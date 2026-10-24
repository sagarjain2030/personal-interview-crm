import logging
import os
import sqlite3 as sql
import pathlib
import uuid
from datetime import datetime, timezone

BASE_DIR = pathlib.Path(__file__).parent.absolute()
SCHEMA_PATH =  pathlib.Path(BASE_DIR, 'schema.sql')
# INTERVIEW_CRM_DB_PATH lets automated tests point the app at an isolated database.
DB_PATH = pathlib.Path(os.environ.get("INTERVIEW_CRM_DB_PATH", BASE_DIR / 'data' / 'interview_crm.db'))

# PRAGMA user_version: 0 = original single-user schema, 1 = multi-user schema (schema.sql).
SCHEMA_VERSION = 1
LEGACY_TABLES = ["resume_versions", "applications", "interviews", "interview_questions"]

GOOGLE_SUB_MAX_LENGTH = 255
# Server-side size limits: anyone with a Google account can sign up, so stored text is bounded.
FIELD_LIMITS = {
    "company": ("Company", 200),
    "role": ("Role", 200),
    "raw_job_description": ("Job Description", 50_000),
    "jd_url": ("Job URL", 2_000),
    "location": ("Location", 200),
    "notes": ("Notes", 20_000),
    "question": ("Interview question", 20_000),
    "apparent_answer": ("My Answer", 20_000),
    "better_answer": ("Better Answer", 20_000),
    "name": ("Name", 200),
}

# Columns returned by get_application_by_id, in the order main.py indexes them (user_id is internal).
APPLICATION_COLUMNS = ("id, company, role, raw_job_description, jd_url, location, notes, created_at, "
                       "applied_date, status, resume_version_id, priority, jd_analysis_json, jd_analysis_status")

logger = logging.getLogger(__name__)


class InvalidIdentityError(ValueError):
    """The signed-in account has no usable Google `sub` claim."""


class ValidationError(ValueError):
    """User input was rejected; the message is safe to show to the user."""


class NotFoundError(LookupError):
    """The record does not exist or belongs to another user (deliberately indistinguishable)."""


class MigrationError(RuntimeError):
    """The database cannot be upgraded automatically; the message explains the manual step."""


def get_connection():
    conn = sql.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def validate_google_sub(google_sub):
    """Return the Google `sub` claim if it is a usable account identifier, else raise InvalidIdentityError."""
    if (not isinstance(google_sub, str) or not google_sub or google_sub != google_sub.strip()
            or len(google_sub) > GOOGLE_SUB_MAX_LENGTH or not google_sub.isprintable()):
        raise InvalidIdentityError("Missing or invalid Google account identifier.")
    return google_sub


def _check_lengths(**fields):
    for field, value in fields.items():
        label, limit = FIELD_LIMITS[field]
        if value is not None and len(value) > limit:
            raise ValidationError(f"{label} must be at most {limit:,} characters.")


def _optional_claim(value, limit=320):
    """Profile claims are display-only; keep them only if they are reasonable strings."""
    return value if isinstance(value, str) and value and len(value) <= limit else None


def _now():
    return datetime.now(timezone.utc).isoformat()


def _write(statement, params, not_found_message=None):
    """Run one write statement in a transaction. If it matched no row, raise NotFoundError."""
    conn = get_connection()
    try:
        with conn:
            cursor = conn.execute(statement, params)
            if not_found_message and cursor.rowcount == 0:
                raise NotFoundError(not_found_message)
    finally:
        conn.close()


def _read(statement, params, fetch_one=False):
    conn = get_connection()
    try:
        cursor = conn.execute(statement, params)
        return cursor.fetchone() if fetch_one else cursor.fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------------------------
# Schema creation and migration
# ---------------------------------------------------------------------------------------------

def init_db(legacy_owner_google_sub=None):
    """Create the schema on a fresh database, or upgrade a single-user database to multi-user.

    Upgrading assigns every existing record to `legacy_owner_google_sub` (the account that used the
    single-user version). It writes a backup next to the database first and runs in one transaction,
    so a failure leaves the database exactly as it was. Safe to call on every run and concurrently.
    """
    pathlib.Path(DB_PATH.parent).mkdir(parents=True, exist_ok=True)
    # autocommit=True: transactions are controlled explicitly below, and foreign keys stay off
    # (the default) so tables can be rebuilt; PRAGMA foreign_key_check validates the result.
    conn = sql.connect(DB_PATH, autocommit=True)
    try:
        if _user_version(conn) == SCHEMA_VERSION:
            return
        conn.execute("BEGIN IMMEDIATE")  # one initializer at a time; others wait, then see the new version
        try:
            version = _user_version(conn)
            if version > SCHEMA_VERSION:
                raise MigrationError(f"Database schema version {version} is newer than this application "
                                     f"supports ({SCHEMA_VERSION}).")
            if version < SCHEMA_VERSION:
                if _is_legacy_schema(conn):
                    _migrate_legacy_schema(conn, legacy_owner_google_sub)
                else:
                    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
                if conn.execute("PRAGMA foreign_key_check").fetchall():
                    raise MigrationError("Foreign key check failed after the upgrade; nothing was changed.")
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        # WAL lets readers continue while another session writes; it must be set outside a transaction.
        # It is persistent and best effort: if another connection is busy, a later start-up sets it.
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sql.OperationalError:
            pass
    finally:
        conn.close()


def _user_version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _table_columns(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _is_legacy_schema(conn):
    columns = _table_columns(conn, "applications")
    return bool(columns) and "user_id" not in columns


def _backup_database():
    """Copy the database next to it before migrating, and return the backup path.

    Uses its own connection: the migrating connection holds a write lock, and SQLite's backup
    cannot read through a connection that is writing (a separate reader is allowed).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = DB_PATH.with_name(f"{DB_PATH.stem}.pre-multi-user-{timestamp}{DB_PATH.suffix or '.db'}")
    if backup_path.exists():
        raise MigrationError(f"Backup file {backup_path.name} already exists; nothing was changed.")
    source, target = sql.connect(DB_PATH), sql.connect(backup_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup_path


def _check_legacy_columns_are_kept(conn, tables):
    """Refuse to migrate a table with columns schema.sql does not have, instead of dropping their data."""
    scratch = sql.connect(":memory:")
    try:
        scratch.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        for table in tables:
            unknown = set(_table_columns(conn, table)) - set(_table_columns(scratch, table))
            if unknown:
                raise MigrationError(f"Table {table} has columns the new schema does not have "
                                     f"({', '.join(sorted(unknown))}); nothing was changed.")
    finally:
        scratch.close()


def _migrate_legacy_schema(conn, legacy_owner_google_sub):
    """Rebuild version-0 tables from schema.sql, assigning all existing rows to the legacy owner.

    Runs inside the caller's transaction: any exception rolls everything back.
    """
    present = [t for t in LEGACY_TABLES if _table_columns(conn, t)]
    _check_legacy_columns_are_kept(conn, present)
    row_counts = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in present}
    has_data = any(row_counts.values())

    owner_id = None
    if has_data:
        try:
            owner_sub = validate_google_sub(legacy_owner_google_sub)
        except InvalidIdentityError:
            raise MigrationError(
                "This database was created by the single-user version and contains records, but no "
                "legacy owner is configured. Back up the database, then set [access] allowed_google_sub "
                "in the Streamlit secrets to the Google `sub` of the account that owns these records "
                "and restart the app. Nothing was changed.") from None
        backup_path = _backup_database()
        logger.warning("Backed up the single-user database to %s before migrating.", backup_path)
        owner_id = str(uuid.uuid4())

    # Renaming a table also rewrites foreign keys that point at it, so every legacy table is renamed
    # and rebuilt; legacy indexes are dropped so schema.sql can recreate them on the new tables.
    for (index_name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL AND tbl_name IN "
            f"({','.join('?' * len(present))})", present).fetchall():
        conn.execute(f'DROP INDEX "{index_name}"')
    for table in present:
        conn.execute(f"ALTER TABLE {table} RENAME TO legacy_{table}")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    if owner_id:
        conn.execute("INSERT INTO users (id, google_sub, email, name, created_at) VALUES (?, ?, NULL, NULL, ?)",
                     (owner_id, owner_sub, _now()))
    for table in present:
        legacy_columns = _table_columns(conn, f"legacy_{table}")
        new_columns = [c for c in _table_columns(conn, table) if c in legacy_columns]
        column_list = ", ".join(new_columns)
        if table in ("resume_versions", "applications"):
            conn.execute(f"INSERT INTO {table} (user_id, {column_list}) "
                         f"SELECT ?, {column_list} FROM legacy_{table}", (owner_id,))
        else:
            conn.execute(f"INSERT INTO {table} ({column_list}) SELECT {column_list} FROM legacy_{table}")
        copied = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        if copied != row_counts[table]:
            raise MigrationError(f"Row count mismatch while migrating {table}; nothing was changed.")
    for table in reversed(present):
        conn.execute(f"DROP TABLE legacy_{table}")
    logger.warning("Migrated the database to schema version %s (%s).", SCHEMA_VERSION,
                ", ".join(f"{t}: {n} rows" for t, n in row_counts.items()))


# ---------------------------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------------------------

def get_or_create_user(google_sub, email=None, name=None):
    """Return the internal user id for a Google account, registering it on first sign-in.

    Identity is the Google `sub` claim only; email and name are stored for display. The UNIQUE
    constraint plus an upsert make concurrent first sign-ins of the same account safe.
    """
    google_sub = validate_google_sub(google_sub)
    email, name = _optional_claim(email), _optional_claim(name)
    conn = get_connection()
    try:
        row = conn.execute("SELECT id, email, name FROM users WHERE google_sub = ?", (google_sub,)).fetchone()
        if row and (email is None or email == row[1]) and (name is None or name == row[2]):
            return row[0]  # common case: no write on every Streamlit rerun
        with conn:
            row = conn.execute(
                "INSERT INTO users (id, google_sub, email, name, created_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (google_sub) DO UPDATE SET email = coalesce(excluded.email, users.email), "
                "name = coalesce(excluded.name, users.name) RETURNING id",
                (str(uuid.uuid4()), google_sub, email, name, _now())).fetchone()
        return row[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------------------------
# Applications. Every function takes the signed-in user's internal id and only touches their rows.
# ---------------------------------------------------------------------------------------------

def create_application(
    user_id,
    company,
    role,
    raw_job_description=None,
    jd_url=None,
    location=None,
    notes=None
):
    _check_lengths(company=company, role=role, raw_job_description=raw_job_description,
                   jd_url=jd_url, location=location, notes=notes)
    application_id = str(uuid.uuid4())
    insert_stmt = """
        INSERT INTO applications (id,user_id,company,role,raw_job_description,
            jd_url,location,notes,created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    _write(insert_stmt, (application_id, user_id, company, role, raw_job_description,
                         jd_url, location, notes, _now()))
    return application_id


def get_all_applications(user_id):
    return _read("SELECT id,company,role,status,created_at FROM applications "
                 "WHERE user_id=? ORDER BY created_at DESC", (user_id,))


def get_application_by_id(user_id, application_id):
    """The application row, or None if it does not exist or belongs to another user."""
    return _read(f"SELECT {APPLICATION_COLUMNS} FROM applications WHERE id=? AND user_id=?",
                 (application_id, user_id), fetch_one=True)


def update_application_status(user_id, application_id, new_status):
    _write("UPDATE applications SET status = ? WHERE id=? AND user_id=?",
           (new_status, application_id, user_id), "Application not found.")


def update_application_priority(user_id, application_id, new_priority):
    _write("UPDATE applications SET priority = ? WHERE id=? AND user_id=?",
           (new_priority, application_id, user_id), "Application not found.")


def update_application_details(user_id, application_id, company, role, raw_job_description, jd_url, location, notes):
    _check_lengths(company=company, role=role, raw_job_description=raw_job_description,
                   jd_url=jd_url, location=location, notes=notes)
    _write("UPDATE applications SET company = ?, role = ?, raw_job_description = ?, jd_url = ?, "
           "location = ?, notes = ? WHERE id = ? AND user_id = ?",
           (company, role, raw_job_description, jd_url, location, notes, application_id, user_id),
           "Application not found.")


# ---------------------------------------------------------------------------------------------
# Resume versions (owned directly by a user)
# ---------------------------------------------------------------------------------------------

def create_resume_version(user_id, name, notes=None):
    _check_lengths(name=name, notes=notes)
    resume_version_id = str(uuid.uuid4())
    _write("INSERT INTO resume_versions (id, user_id, name, notes, created_at) VALUES (?, ?, ?, ?, ?)",
           (resume_version_id, user_id, name, notes, _now()))
    return resume_version_id


def get_resume_versions(user_id):
    return _read("SELECT id, name, notes, created_at FROM resume_versions WHERE user_id=? "
                 "ORDER BY created_at DESC", (user_id,))


def set_application_resume_version(user_id, application_id, resume_version_id):
    """Link one of the user's resumes (or None) to one of their applications."""
    _write("UPDATE applications SET resume_version_id = ? WHERE id = ? AND user_id = ? AND (? IS NULL OR "
           "EXISTS (SELECT 1 FROM resume_versions WHERE id = ? AND user_id = ?))",
           (resume_version_id, application_id, user_id, resume_version_id, resume_version_id, user_id),
           "Application or resume not found.")


# ---------------------------------------------------------------------------------------------
# Interviews and questions: ownership is checked through the parent application in the same statement.
# ---------------------------------------------------------------------------------------------

def create_interview(
    user_id,
    application_id,
    round_number,
    round_type
):
    interview_id = str(uuid.uuid4())
    # INSERT ... SELECT inserts nothing unless the application belongs to this user.
    insert_stmt = """
        INSERT INTO interviews (id,application_id,round_type,round_number)
            SELECT ?, id, ?, ? FROM applications WHERE id=? AND user_id=?
    """
    _write(insert_stmt, (interview_id, round_type, round_number, application_id, user_id),
           "Application not found.")
    return interview_id


def get_interviews_by_application_id(user_id, application_id):
    return _read("SELECT i.id, i.round_number, i.round_type, i.result FROM interviews i "
                 "JOIN applications a ON a.id = i.application_id "
                 "WHERE i.application_id=? AND a.user_id=? ORDER BY i.round_number ASC, i.rowid ASC",
                 (application_id, user_id))


def create_interview_question(
    user_id,
    interview_id,
    question,
    apparent_answer=None,
    better_answer=None
):
    _check_lengths(question=question, apparent_answer=apparent_answer, better_answer=better_answer)
    question_id = str(uuid.uuid4())
    insert_stmt = """
        INSERT INTO interview_questions (id,interview_id,question,apparent_answer,better_answer)
            SELECT ?, i.id, ?, ?, ? FROM interviews i JOIN applications a ON a.id = i.application_id
            WHERE i.id=? AND a.user_id=?
    """
    _write(insert_stmt, (question_id, question, apparent_answer, better_answer, interview_id, user_id),
           "Interview not found.")
    return question_id


def get_questions_by_interview_id(user_id, interview_id):
    # interview_questions has no created_at column; rowid preserves insertion order.
    return _read("SELECT q.id, q.question, q.apparent_answer, q.better_answer FROM interview_questions q "
                 "JOIN interviews i ON i.id = q.interview_id JOIN applications a ON a.id = i.application_id "
                 "WHERE q.interview_id=? AND a.user_id=? ORDER BY q.rowid ASC",
                 (interview_id, user_id))
