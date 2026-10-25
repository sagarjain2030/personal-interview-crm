# Personal Interview CRM

A multi-user application for organizing a personal job search and learning from interview experiences. Built with Python, Streamlit, and SQLite, the project is designed to grow incrementally into an AI-assisted interview preparation tool.

## Project goals

- Keep job applications and their job descriptions in one place.
- Record interview rounds and questions as those features are developed.
- Identify recurring knowledge gaps and track improvement over time.
- Learn Python, Streamlit, SQLite, and AI integration through a practical project.

The planned workflow is:

**Job Application → Job Description → Interview Rounds → Questions → Knowledge Gaps → Improvement Tracking**

## Current features

**Implemented (through Step 7):**

- Streamlit navigation with **Jobs**, **Interviews**, **Questions**, and **Insights** sections.
- **Jobs:** add an application (company, role, full job description, JD URL, location, notes) with required-field validation; list saved applications; select one to edit its details, status, and priority.
- **Interviews:** select an application, add interview rounds (round number and round type), and view that application's rounds ordered by round number with readable round-type and result labels. New rounds default to the *Scheduled* result.
- **Questions:** select an application and one of its interview rounds, add a question with your actual answer and an optional better answer, and view that round's saved questions in the order they were added.
- **Sign-in with Google** (Streamlit OIDC). Any Google account can register; each account gets its own private workspace, enforced in the database layer. See [SECURITY_AND_DEPLOYMENT.md](SECURITY_AND_DEPLOYMENT.md).
- The database is created automatically from `schema.sql` on first run; a database from the single-user version is upgraded once (with a backup), its records assigned to the configured legacy owner.
- Local SQLite storage with UUID primary keys, integer-coded status/type/result values, and success/error messages for database operations.

**Not implemented yet:** Interview and question editing/deletion, topics and knowledge-gap tracking, insights, and AI-powered analysis. The Insights section currently contains a placeholder.

## Tech stack

- **Python** — application and database logic
- **Streamlit** — user interface
- **SQLite** (via Python's built-in `sqlite3`) — local data persistence

Hugging Face integration and optional Pydantic validation are being considered for later stages; neither is part of the current working functionality.

## Project structure

```text
personal-interview-crm/
├── main.py             # Streamlit interface and navigation
├── db.py               # SQLite connection, initialization, inserts, and queries
├── schema.sql          # Database table definitions (multi-user, schema version 1)
├── backup_db.py        # Online SQLite backup and verification (python backup_db.py backup|verify)
├── serve.py            # Production start: secrets from STREAMLIT_SECRETS_TOML, then streamlit run├── SECURITY_AND_DEPLOYMENT.md # Ownership model, migration, abuse protection, Google/Railway setup
├── .streamlit/         # config.toml (committed) and secrets.toml (Git-ignored; see secrets.toml.example)
├── requirements.txt    # Python dependencies
├── requirements-dev.txt # Test dependencies (pytest, Playwright)
├── pytest.ini          # Test configuration
├── TESTING.md          # How to run the tests
├── tests/              # db/, apptest/ and e2e/ (browser) tests
├── .githooks/pre-push  # Runs the full test suite before git push (opt-in)
├── .github/workflows/  # tests.yml (CI) and daily-commit.yml
├── .gitignore          # Local files excluded from Git
└── data/               # Local database directory (not committed)
```

## Getting started

1. Clone the repository and change into the project directory.
2. Create and activate a Python virtual environment.
3. Install the dependencies.
4. Run the Streamlit application.

On Linux or macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then fill in your Google OAuth values
streamlit run main.py
```

The app opens locally in your browser. After sign-in it calls `init_db()` from `db.py`, which creates `data/interview_crm.db` from `schema.sql` if needed. A database created by the single-user version is migrated once: a backup is written next to it first, and all existing records go to the account in `[access] allowed_google_sub`. See [SECURITY_AND_DEPLOYMENT.md](SECURITY_AND_DEPLOYMENT.md) before upgrading real data.

## Testing

Automated tests cover Steps 1–7 at three levels: database, Streamlit AppTest, and real-browser Playwright. They always run against temporary databases, never `data/interview_crm.db`.

```bash
pip install -r requirements-dev.txt
playwright install chromium
pytest                  # all tests, headless
pytest -m "not e2e"     # skip the browser tests
pytest tests/e2e --headed --slowmo 500 -v   # watch the browser tests
git config core.hooksPath .githooks         # once per clone: test before every push
```

GitHub Actions (`.github/workflows/tests.yml`) runs the full suite on every push and pull request. See [TESTING.md](TESTING.md) for details.

## Local data and privacy

Application records, job descriptions, and interview notes are stored in a **SQLite database** (local, or on a Railway volume in production), never in this GitHub repository. Each record belongs to one Google account and is only visible to it. The `.gitignore` excludes database files, virtual environments, Python cache files, and local environment configuration files.

If you fork or clone this project, your personal data is not included. Review files before committing to ensure no credentials or personal records have been added to tracked source files.

## Development status

- **Steps 1–5: Complete** — setup, schema, add/list/view/edit applications, status and priority.
- **Step 6: Complete** — record interview rounds for an application and list them with readable labels.
- **Step 7: Complete** — record interview questions with actual and better answers per interview round.
- **Step 8: Not started** — recurring interview questions and knowledge gaps.

## Project approach

This is a personal learning project; the multi-user V1 is designed to be deployed on Railway with a single SQLite volume. Development is intentionally incremental, with a small local architecture and manual verification of each completed feature before moving to the next step.