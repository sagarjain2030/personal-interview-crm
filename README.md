# Personal Interview CRM

A local-first, single-user application for organizing a personal job search and learning from interview experiences. Built with Python, Streamlit, and SQLite, the project is designed to grow incrementally into an AI-assisted interview preparation tool.

## Project goals

- Keep job applications and their job descriptions in one place.
- Record interview rounds and questions as those features are developed.
- Identify recurring knowledge gaps and track improvement over time.
- Learn Python, Streamlit, SQLite, and AI integration through a practical project.

The planned workflow is:

**Job Application → Job Description → Interview Rounds → Questions → Knowledge Gaps → Improvement Tracking**

## Current features

**Implemented (through Step 3):**

- Streamlit navigation with **Jobs**, **Interviews**, **Questions**, and **Insights** sections.
- An **Add Application** form in the Jobs section, with fields for company, role, full job description, JD URL, location, and notes.
- Required-field validation for company and role.
- Local SQLite storage for newly created applications.
- Unique application IDs, UTC creation timestamps, and database defaults.
- Preservation of the original multiline job description.
- Success and database-error messages when saving an application.

**Not implemented yet:** Application listing/editing, interview and question management, insights, knowledge-gap tracking, and AI-powered analysis. The Interviews, Questions, and Insights sections currently contain placeholders.

## Tech stack

- **Python** — application and database logic
- **Streamlit** — user interface
- **SQLite** (via Python's built-in `sqlite3`) — local data persistence

Hugging Face integration and optional Pydantic validation are being considered for later stages; neither is part of the current working functionality.

## Project structure

```text
personal-interview-crm/
├── main.py             # Streamlit interface and navigation
├── db.py               # SQLite connection, initialization, and inserts
├── schema.sql          # Database table definitions
├── requirements.txt    # Python dependencies
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
streamlit run main.py
```

The app opens locally in your browser. On a fresh setup, the SQLite tables must be initialized using the project's `init_db()` helper in `db.py` if your startup flow does not already call it. The helper reads `schema.sql` and creates the local database as needed.

## Local data and privacy

Application records, job descriptions, and future interview notes are intended to remain in a **local SQLite database**, not in this GitHub repository. The `.gitignore` excludes database files, virtual environments, Python cache files, and local environment configuration files.

If you fork or clone this project, your personal data is not included. Review files before committing to ensure no credentials or personal records have been added to tracked source files.

## Development status

**Step 3: Complete — Manual Add Job/Application.**

The application form, SQLite insertion, validation, and persistence were verified. One verification remains outstanding: checking database record counts before and after sidebar navigation and browser refresh to independently confirm that those actions do not create duplicate records.

**Step 4: Not started.** Its scope will be defined by the project roadmap before implementation.

## Project approach

This is a personal learning project, not a production SaaS product. Development is intentionally incremental, with a small local architecture and manual verification of each completed feature before moving to the next step.