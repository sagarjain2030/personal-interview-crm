# Security, Multi-User Data Model and Deployment

## 1. Identity and ownership model

- **Sign-in:** Streamlit's built-in OIDC (`st.login()` / `st.logout()`) with Google. After login Streamlit
  keeps the ID-token claims in an HTTP-only cookie signed with `[auth] cookie_secret`.
- **Registration:** any Google account can sign in. On every script run `main.py` reads `st.user["sub"]`,
  validates it (`db.validate_google_sub`: non-empty string, no surrounding whitespace, printable, ≤ 255
  chars) and calls `db.get_or_create_user()`. A missing/invalid `sub` shows "Access Denied" before the
  database is opened.
- **Identity = Google `sub` only.** `email` and `name` are stored for display and never used to look a
  user up. Two accounts with the same email are two users.
- **Internal id:** `users.id` (a UUID) is resolved on the server on every run and passed explicitly to
  the render functions. It is never read from widgets, query parameters or `st.session_state`.

```text
users ─┬─< applications ─< interviews ─< interview_questions
       └─< resume_versions
applications.(resume_version_id, user_id) ──> resume_versions.(id, user_id)
```

| Table | Owner | How it is enforced |
|---|---|---|
| `applications` | `user_id` column (NOT NULL, FK → users) | every query has `AND user_id = ?` |
| `resume_versions` | `user_id` column (NOT NULL, FK → users) | every query has `user_id = ?` |
| `interviews` | parent application | reads `JOIN applications … AND a.user_id = ?`; writes are `INSERT … SELECT … FROM applications WHERE id = ? AND user_id = ?` |
| `interview_questions` | interview → application | same, through both joins |

**Cross-user references are impossible at two levels:** the data layer checks ownership in the same SQL
statement as the write (no check-then-act race), and the schema's composite foreign key
`(resume_version_id, user_id) → resume_versions(id, user_id)` makes SQLite itself reject linking another
user's resume. Interviews and questions carry no `user_id`, so there is nothing to get out of sync.

**Denials:** a write that matches no owned row raises `db.NotFoundError`; reads return `None`/`[]`. A
foreign record and a non-existent record are indistinguishable (no existence oracle). The UI shows
"The selected record could not be found."

## 2. Database schema and migrations

`PRAGMA user_version` records the schema version: `0` = original single-user schema, `1` = multi-user.

`db.init_db(legacy_owner_google_sub)` runs on every script run, after authentication:

1. Version already 1 → return immediately (one cheap read).
2. Otherwise take a write lock (`BEGIN IMMEDIATE`) and re-check, so concurrent sessions migrate once.
3. **Fresh database** → run `schema.sql`.
4. **Version-0 database** →
   - refuse if any legacy table has a column the new schema lacks (data would be lost);
   - if it contains records, require a valid legacy owner `sub`, otherwise stop with `MigrationError`
     (nothing changed);
   - write a backup next to the database: `interview_crm.pre-multi-user-<UTC timestamp>.db`;
   - rename the legacy tables, create the new ones from `schema.sql`, copy every row (resumes and
     applications get the owner's `user_id`), verify row counts, drop the old tables;
   - `PRAGMA foreign_key_check` must be empty.
5. Set `user_version = 1` and `COMMIT`. Any error → `ROLLBACK`: the database is exactly as before.
6. Switch to WAL journal mode (readers no longer block on a writer).

Because the migrated tables are created from the same `schema.sql`, a migrated database is identical to
a fresh one (tested).

### Legacy records: who gets them

Existing records belong to the original single-user account. They are **never** given to whoever signs
in first. The owner is the Google `sub` in the existing secret:

```toml
[access]
allowed_google_sub = "<the sub you used before>"
```

This key is no longer an allowlist; it is read only to perform the one-time upgrade. A `users` row is
created for that `sub` (email/name empty until that person signs in). If your secrets already contain
this value (they did for the single-user version), the upgrade happens automatically on the next start.

If the database holds records and the key is missing/invalid, every signed-in user sees "The CRM
database needs a one-time upgrade by the administrator" and the server log explains the fix.

### Migration runbook (real data)

1. Stop the app.
2. Make your own backup in addition to the automatic one:
   `sqlite3 data/interview_crm.db ".backup 'data/interview_crm.manual-backup.db'"`
   (or copy the file while the app is stopped).
3. Confirm `[access] allowed_google_sub` is the `sub` of the account that owns the data.
4. Start the app and sign in with that account; check your applications, interviews and questions.
5. Sign in with a second Google account (or a private window) and confirm it sees an empty workspace.
6. Keep the backup file until you are satisfied. To roll back: stop the app, restore the backup
   file over `interview_crm.db` (delete `interview_crm.db-wal`/`-shm` too), and run the previous version.

If the wrong `sub` was configured, the data is not lost; fix it with:
`UPDATE users SET google_sub = '<correct sub>' WHERE google_sub = '<wrong sub>';`
(only if the correct account has not signed in yet; otherwise reassign `applications.user_id` and
`resume_versions.user_id`).

## 3. Security controls in the application

- Authentication gate before any database access; identity re-resolved on every run.
- Ownership enforced in `db.py` for every operation (Section 1); a test fails if a new public data
  function does not take `user_id` first.
- All SQL is parameterized. Table names interpolated in migration code come from a fixed list.
- `UNIQUE (google_sub)` + `INSERT … ON CONFLICT DO UPDATE … RETURNING`: concurrent first logins of the
  same account produce one user.
- Server-side length limits on all text fields (`db.FIELD_LIMITS`, e.g. Job Description 50,000 chars)
  to bound storage use by open registration.
- Error messages are generic; SQL errors, file paths and stack traces go only to the server log
  (`logger.exception`). Nothing logs tokens, cookies or secrets.
- User text is shown with `st.text`, `st.dataframe` and widget values; nothing uses
  `unsafe_allow_html`. (The edit preview and display name use Markdown, so a user can format their
  *own* text; it is never shown to other users.)
- No `st.cache_data`/`st.cache_resource` (they are shared across users and would leak data).
- `.streamlit/config.toml` keeps CORS and XSRF protection on, sets `maxUploadSize = 1` (no uploads)
  and `maxMessageSize = 20` MB (default 200).
- Short write transactions, a 5 s busy timeout (sqlite3 default) and WAL mode for concurrency.

## 4. Remaining risks (accepted for V1 or need a decision)

- **Stateless session cookie:** Streamlit's auth cookie is valid for 30 days. Logout deletes it from the
  browser, but a stolen copy remains valid until it expires or `cookie_secret` is rotated (rotating
  signs everyone out). There is no server-side session revocation.
- **No per-user quotas:** a user can create many records within the field limits. Monitor volume usage;
  add a per-user row cap if abuse appears.
- **Single provider assumption:** `sub` is unique per issuer. If another OIDC provider is ever added,
  store the issuer with the `sub`.
- **SQLite on one volume:** one instance only (Railway volumes do not support replicas); brief downtime
  on each redeploy; database-level backups are your responsibility (see Railway backups).
- **Legacy owner misconfiguration:** a wrong `sub` assigns old data to an account nobody uses; data
  stays recoverable (Section 2).
- **Account deletion / data export** (privacy requests from external users) is not implemented.
- **`resume_versions.file_path`** exists in the schema but is not written by the app. Never open a
  file path that came from user input if file uploads are added later.
- **Uncaught exceptions** show Streamlit's error box with a traceback in local development; the
  production start (`serve.py`) sets `client.showErrorDetails = none` (Section 7).

## 5. DDoS and abuse protection — who does what

Python code cannot prevent a DDoS: by the time a request reaches the app, the bandwidth and connections
are already used. No homemade rate limiter was added (it would be per-process, reset on deploy, and
blind to traffic that never reaches Python).

| Layer | Protection | Status |
|---|---|---|
| **App (Python)** | Login required before any DB access; per-user isolation; field length limits; generic errors | Implemented |
| **Streamlit** | Signed HTTP-only auth cookie; CORS + XSRF protection; WebSocket message size limit; upload limit | Enabled (`config.toml`) |
| **Google** | Account creation and sign-in abuse controls are Google's (CAPTCHA, risk checks) | External, automatic |
| **Railway edge** | TLS 1.2+/1.3 with automatic certificates; Railway Metal mitigates network layer 4 and below; built-in limits (≈11,000 req/s per domain, 10,000 concurrent connections, 32 KB headers) | Automatic |
| **Railway WAF** | *Under Attack Mode*: browser check for every new visitor, blocks non-browser traffic; on demand, 1–24 h or until disabled (Service → Settings → Edge, or `railway waf under-attack enable --service <name>`) | Manual, use during an incident |
| **External (optional)** | Always-on L7 rate limiting / bot rules (e.g. a CDN/WAF in front of a custom domain) | Not added; only if Railway's controls prove insufficient |

Note: Streamlit pages are served before login, and each visitor opens a WebSocket, so an unauthenticated
flood can still consume server memory/CPU. Railway's limits and Under Attack Mode are the right controls.
Also set Railway usage limits / alerts so an attack cannot create an unbounded bill.

## 6. Google Cloud configuration (manual)

1. Google Cloud Console → *APIs & Services* → *OAuth consent screen* (Google Auth Platform):
   - User type **External**; app name, support email, developer contact.
   - Scopes: only `openid`, `email`, `profile` (Streamlit's default). These are non-sensitive.
   - Add links to a privacy policy and terms page and your app domain (needed for publishing/branding).
   - While in **Testing**, only listed test users (max 100) can sign in. To allow anyone, **Publish app**
     → *In production*. Google may require brand verification; complete it if prompted.
2. *Credentials* → OAuth client ID → **Web application**:
   - Authorized redirect URIs: `http://localhost:8501/oauth2callback` (local) and
     `https://<your-railway-or-custom-domain>/oauth2callback` (production). Must match
     `[auth] redirect_uri` exactly.
   - Consider separate OAuth clients for local and production.
   - Use a subdomain of the verified `sagarjain.in` (e.g. `crm.sagarjain.in`, a Railway custom domain) for
     production, not `*.up.railway.app`: `up.railway.app` is a public suffix, so each Railway hostname
     would be a separate domain that has to be added to *Authorized domains* and verified by you for
     branding verification.
3. Never commit the client secret. If it is ever exposed, rotate it in the console.

To find your own `sub` for `allowed_google_sub`: sign in to the *old* version locally and temporarily
print `st.user.get("sub")` in a local-only session, or decode the ID token you receive locally. Do not
log it in production.

## 7. Railway configuration (manual)

All service settings are made in the Railway dashboard. New services cannot use `railway.toml` /
`railway.json` (config-as-code is closed to new services; legacy support ends 2026-12-01), and no
`.railway/` infrastructure-as-code is used. Railpack builds the app (`.python-version` pins 3.14.6).
`serve.py` starts Streamlit on `$PORT` with tracebacks hidden from visitors (`showErrorDetails = none`).

1. Create a service from the GitHub repository, trigger branch `main`. Keep replicas at 1.
   In the service's Settings page:
   - **Deploy → Custom Start Command:** `python serve.py`. Required: without it Railpack runs
     `python main.py`, which does not start the Streamlit server.
   - **Deploy → Healthcheck Path:** `/_stcore/health` (default timeout 300 s is enough).
   - **Deploy → Restart Policy:** *On Failure* (Railway's default; max 10 retries on free/trial plans).
   - **Build → Watch Paths** (optional, recommended): one pattern per line,
     ```text
     **
     !/log.txt
     ```
     The *Daily Commit* workflow changes only `log.txt` and its pushes start no Tests run (they use
     `GITHUB_TOKEN`), so without this rule every daily commit would redeploy and briefly restart
     production without passing through Wait for CI. Every other change still deploys. Railway applies
     negations only after a preceding include rule, hence the `**` line.
2. **Volume:** add one volume to the service, mount path `/data`. Expect a short downtime on each redeploy.
3. **Variables** (Service → Variables):
   - `INTERVIEW_CRM_DB_PATH=/data/interview_crm.db`
   - `STREAMLIT_SECRETS_TOML`: the complete production `secrets.toml` (multi-line value) with a **new**
     `cookie_secret` (≥ 32 characters, never the local one), the production client ID/secret, and
     `redirect_uri = "https://<domain>/oauth2callback"`. `serve.py` refuses to start (without printing any
     value) if it is missing, not TOML, lacks an `[auth]` key, or has a non-HTTPS redirect URI or a short
     cookie secret. It writes the secrets to a `0600` temporary file outside the repository and removes
     the variable from Streamlit's environment.
4. **Domain:** add the custom domain (Service → Settings → Networking), then register its
   `https://<domain>/oauth2callback` in the Google OAuth client (Section 6).
5. **Wait for CI:** Service → Settings → enable *Wait for CI* (shown once Railway's GitHub app has the
   updated permissions; `tests.yml` runs on every push). A failing Tests run skips the deployment.
   A manual *Redeploy* bypasses this gate.
6. **Migrating existing data:** upload your local database to the volume once (while the service is
   stopped), with `allowed_google_sub` set; the first start migrates it and writes a backup on the volume.
   For a fresh start, simply leave the volume empty.
7. **Backups:** enable volume backups (Volume → Backups; manual and scheduled). For a database-level
   copy, run `python backup_db.py backup /data/backups/interview_crm-<date>.db` in the service shell
   (`railway ssh`), download it, and check it with `python backup_db.py verify <file>`. Test a restore
   once: restore into a separate location, verify, never over the live file while the app runs.
8. Set usage limits/alerts. Know where the WAF toggle is (Service → Settings → Edge → Under Attack Mode)
   before you need it.

## 8. Manual security test checklist

Run against a local server with real Google sign-in, then again on Railway.

- [ ] Visitor without login sees only the sign-in screen; no data, no navigation.
- [ ] First sign-in with account A creates one `users` row (`SELECT * FROM users`), with A's `sub`.
- [ ] Signing in again (other browser/device) reuses A's row; no duplicate.
- [ ] Account B (private window) sees an empty workspace, then creates its own records.
- [ ] A and B each see only their own applications, interviews and questions on every page.
- [ ] Copy an application UUID from A's success message; as B, confirm no page shows it and that B's
      dropdowns never list it.
- [ ] Legacy upgrade: on a *copy* of the old database, start with `allowed_google_sub` set → owner sees all
      old records; another account sees none; a `*.pre-multi-user-*.db` backup exists.
- [ ] Legacy database with the key removed → "needs a one-time upgrade" message; file unchanged.
- [ ] Logout returns to the login screen; refresh stays logged out; Back button does not show data.
- [ ] Error paths (e.g. read-only database file) show generic messages without paths or SQL.
- [ ] Very long input (e.g. 60,000-character job description) is rejected with a clear message.
- [ ] Browser dev tools: the `_streamlit_user` cookie is HttpOnly; nothing secret in page source.
- [ ] Production: HTTPS only, redirect URI matches, tracebacks hidden, secrets not in the repository
      (`git log -p | grep -i secret` shows only placeholders).
- [ ] Under Attack Mode can be enabled and disabled; the app still works for browsers while it is on.
