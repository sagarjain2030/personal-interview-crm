# Testing Guide

The test suite has three layers, all run with **pytest**:

| Layer | Folder | Tool | What it checks |
|---|---|---|---|
| Database | `tests/db/` | pytest + `sqlite3` | `db.py` helpers, schema defaults, constraints, foreign keys, user registration, cross-user isolation, migrations |
| App (simulated) | `tests/apptest/` | Streamlit `AppTest` | Page logic, forms, validation messages, error handling, without a browser |
| Browser (end-to-end) | `tests/e2e/` | Playwright + Chromium | The real app served by `streamlit run`, driven through visible controls |

## Setup (once)

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
playwright install chromium
```

## Running tests

Full suite, headless (the browser runs invisibly; this is what the pre-push hook and CI run):

```bash
pytest                      # all three layers, ~100 s
pytest -v                   # same, one line per test
```

Single layers:

```bash
pytest tests/db             # database layer
pytest tests/apptest        # Streamlit AppTest layer
pytest tests/e2e            # real browser, headless Chromium
pytest -m "not e2e"         # fast run without the browser
pytest tests/e2e/test_e2e_jobs.py -k edit -v   # a single test
```

Watch the browser tests in a visible Chromium window (needs a desktop session); `--slowmo 500` pauses 500 ms between actions:

```bash
pytest tests/e2e --headed --slowmo 500 -v
```

## Automatic testing before `git push` (pre-push hook)

`.githooks/pre-push` runs the complete suite (including headless browser tests) and **blocks the push if any test fails**.

**Git hooks are not shared automatically.** Cloning or pulling a repository never activates its hooks, for security reasons. Each clone must opt in once:

```bash
git config core.hooksPath .githooks
```

- Check it: `git config --get core.hooksPath` should print `.githooks`.
- The hook uses `.venv/bin/python` if it exists, otherwise `python3`. If pytest/Playwright are missing, it blocks the push and prints the install commands.
- Tests run on your **working tree**, so uncommitted changes are tested too. The hook prints a note when there are any.
- Emergency bypass (CI will still test the push): `git push --no-verify`
- Uninstall: `git config --unset core.hooksPath`

## Continuous integration (GitHub Actions)

`.github/workflows/tests.yml` runs on every push, every pull request, and on demand ("Run workflow"):

1. Python 3.14, `pip install -r requirements.txt -r requirements-dev.txt`
2. `python -m playwright install --with-deps chromium` (browser plus Linux system libraries)
3. `pytest tests/db`, `pytest tests/apptest` and `pytest tests/e2e` as separate steps. Every layer runs even if an earlier one fails.
4. On failure, `test-results/` (screenshots and traces) is uploaded as the **playwright-test-results** artifact on the run's summary page.

CI has no `data/interview_crm.db`, because it is Git-ignored. The same database guard fails the run if a test creates or changes it. Pushes made by the scheduled *Daily Commit* workflow use `GITHUB_TOKEN`, which by GitHub's design does not trigger other workflows, so those commits do not start test runs.

## Your real database is never used

- `tests/conftest.py` sets `INTERVIEW_CRM_DB_PATH` to a throwaway path **before** `db` is imported. `db.py` reads this variable; when it is not set, the app uses `data/interview_crm.db` as before.
- Every test gets its own fresh database in pytest's temporary folder (the autouse `test_db_path` fixture), initialised from `schema.sql`.
- Browser tests start a separate `streamlit run main.py` process per test, on a free port, with `INTERVIEW_CRM_DB_PATH` pointing at that test's database. The server is stopped after the test.
- A session-level guard hashes `data/interview_crm.db` before and after the run and **fails the run if it changed**.
- AppTest falls back to the real `.streamlit/secrets.toml` when given no secrets, so `tests/app_helpers.py` always sets test-only secrets. Browser tests use a generated secrets file.

## Multi-user and security tests

Every test runs as a simulated Google account: `TEST_USER` by default, `OTHER_USER` as the second account (`tests/auth_helpers.py`). The `owner_id` / `other_user_id` fixtures register them as the app would on first login; data seeded for the signed-in user is created with `owner_id`.

| File | Covers |
|---|---|
| `tests/db/test_db_users.py` | registration, returning users, invalid/missing `sub`, email is not identity, concurrent first sign-in |
| `tests/db/test_db_isolation.py` | adversarial IDOR attempts by direct UUID (reads, updates, nested creates, resume linking), SQL injection in IDs, forged user ids, schema-level FK rejection, a guard that every data function takes `user_id` first |
| `tests/db/test_db_migration.py` | fresh schema, upgrade of a single-user database (`tests/legacy_db.py`), backup, idempotency, rollback on failure, missing owner, concurrent start-ups |
| `tests/apptest/test_app_auth.py` | login gate, registration, rejected identities, logout, identity re-resolved each run |
| `tests/apptest/test_app_multi_user.py` | two accounts in the UI, legacy upgrade at start-up |
| `tests/e2e/test_e2e_auth.py` | real browser: new account, invalid cookie claims, forged cookie, two accounts at once, logout |

The isolation tests were checked by mutation: re-introducing an IDOR bug (e.g. dropping `AND user_id = ?` from any query) makes them fail.

## Failure artifacts

`pytest.ini` keeps a screenshot (`test-failed-1.png`) and a Playwright trace (`trace.zip`) for every failing browser test in `test-results/`. This folder is Git-ignored. To open a trace:

```bash
playwright show-trace test-results/<test-folder>/trace.zip
```

## How the browser tests interact with Streamlit

All browser helpers are in `tests/ui_helpers.py`:
- Elements are found by accessible role and label (`get_by_role`, `get_by_label(..., exact=True)`) and by visible text, not by CSS classes.
- `wait_until_idle()` waits for Streamlit's `data-test-script-state="notRunning"` attribute. Clicks made while the script is still running can be lost.
- `choose()` opens a selectbox and picks an option. If a click only focuses the box, it presses ArrowDown. If a finishing rerun closes the menu, it retries.
- `read_table()` reads an `st.dataframe` through its own **Download as CSV** button, because the grid is drawn on a `<canvas>`. `wait_for_table()` re-reads until the expected rows appear.
- `stApp`, `stDataFrame` and `stException` are Streamlit's published `data-testid` hooks and are the only non-accessibility selectors used.

## What is validated where

- **Browser (Streamlit front-end):** round number must be ≥ 1. The control shows "Number is below the allowed range" and nothing is saved. In AppTest, Streamlit replaces an out-of-range value with the default instead, so that layer only asserts that 0 is never stored.
- **App (`main.py`):** company and role are required, and the question text is required. Whitespace-only values are rejected.
- **Data layer (`db.py`):** ownership of every record, Google `sub` validation, maximum text lengths (`FIELD_LIMITS`).
- **Database (`schema.sql`):** NOT NULL, CHECK ranges (status 0–6, priority 1–3, round_type 0–4, round_number ≥ 1, result 0–3, question priority 1–3), foreign keys (including `(resume_version_id, user_id)` so a resume can only be linked by its owner) and `UNIQUE (google_sub)`. Blank strings are *not* rejected by the database.

## Preparing for future Hugging Face features

No AI code exists yet. When transcription and answer analysis are added, the same structure can test them without downloading models or calling external services:

- **Keep model calls behind one small function or module** (e.g. `ai.py` with `transcribe(audio_path)` and `analyze_answer(question, answer)`). Tests can then `monkeypatch` that function, just as `test_app_error_handling.py` replaces db helpers today.
- **Fake transcription outputs:** fixtures that return fixed transcript strings (including empty, very long, and non-English text) instead of running speech-to-text.
- **Deterministic analysis fixtures:** small JSON files under `tests/fixtures/ai/` with known model responses. Assert that the app stores them correctly, e.g. in `missing_concept`, `better_answer`, `ai_analysis` and `ai_analysis_status`.
- **Invalid or incomplete responses:** fixtures with missing keys, wrong types or malformed JSON. Assert that the UI shows an error and `ai_analysis_status` records a failure instead of crashing.
- **Failures and timeouts:** fakes that raise `TimeoutError` or connection errors. Assert retry/error messaging and that no partial data is saved.
- **Local model checks:** put tests that really load a small model behind a separate marker (e.g. `@pytest.mark.model`) and exclude them by default (`-m "not model"`), so ordinary runs stay fast and offline.
- **Privacy-safe data:** use synthetic transcripts and generated audio (e.g. a short sine tone or text-to-speech of fictional answers). Never commit real interview recordings.
- **Browser tests:** start the Streamlit server with an environment variable that switches the app to the fake AI backend, the same way `INTERVIEW_CRM_DB_PATH` switches the database.
