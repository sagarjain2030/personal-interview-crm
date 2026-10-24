"""Schema initialisation and the one-time upgrade from the single-user database (schema version 0)."""
import sqlite3
import threading

import pytest

import db
from auth_helpers import LEGACY_OWNER_SUB, OTHER_USER
from legacy_db import LEGACY_IDS, LEGACY_SCHEMA_SQL, create_legacy_db

LEGACY_COLUMNS = {
    "resume_versions": "id, name, file_path, notes, created_at",
    "applications": ("id, company, role, raw_job_description, jd_url, location, notes, created_at, applied_date, "
                     "status, resume_version_id, priority, jd_analysis_json, jd_analysis_status"),
    "interviews": ("id, application_id, round_type, round_number, interview_date, interviewer, result, "
                   "confidence, notes, ai_analysis_status, ai_analysis"),
    "interview_questions": ("id, interview_id, question, topic, subtopic, apparent_answer, better_answer, "
                            "missing_concept, priority"),
}


def query(path, sql, params=()):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def schema_of(path):
    return sorted(query(path, "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))


def user_version(path):
    return query(path, "PRAGMA user_version")[0][0]


def legacy_data(path):
    return {table: query(path, f"SELECT {columns} FROM {table} ORDER BY id") for table, columns in LEGACY_COLUMNS.items()}


def backups(path):
    return sorted(path.parent.glob(f"{path.stem}.pre-multi-user-*.db"))


@pytest.fixture
def fresh_schema(tmp_path, monkeypatch):
    """The schema a brand-new database gets, for comparison with a migrated one."""
    with monkeypatch.context() as patch:  # restores db.DB_PATH for the test itself
        path = tmp_path / "reference" / "fresh.db"
        patch.setattr(db, "DB_PATH", path)
        db.init_db()
        return schema_of(path)


@pytest.fixture
def legacy_path(test_db_path, monkeypatch):
    """Replace this test's database with a populated single-user database."""
    create_legacy_db(test_db_path)
    monkeypatch.setattr(db, "DB_PATH", test_db_path)
    return test_db_path


# --- Fresh databases --------------------------------------------------------------------------

def test_fresh_database_gets_the_multi_user_schema(test_db_path):
    tables = {row[0] for row in query(test_db_path, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"users", "resume_versions", "applications", "interviews", "interview_questions"}
    assert user_version(test_db_path) == db.SCHEMA_VERSION
    assert [c[1] for c in query(test_db_path, "PRAGMA table_info(users)")] == [
        "id", "google_sub", "email", "name", "created_at"]
    assert "user_id" in [c[1] for c in query(test_db_path, "PRAGMA table_info(applications)")]
    assert "user_id" in [c[1] for c in query(test_db_path, "PRAGMA table_info(resume_versions)")]
    indexes = {row[0] for row in query(test_db_path, "SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"id_applications_user_id_created_at", "id_resume_versions_user_id", "id_applications_resume_version_id",
            "id_interviews_application_id", "id_interview_questions_interview_id"} <= indexes
    assert query(test_db_path, "PRAGMA journal_mode") == [("wal",)]
    assert backups(test_db_path) == []


def test_fresh_init_is_idempotent_and_keeps_data(test_db_path, owner_id):
    app_id = db.create_application(owner_id, "Keep Co", "Role")
    schema = schema_of(test_db_path)
    for _ in range(3):
        db.init_db(LEGACY_OWNER_SUB)
    assert schema_of(test_db_path) == schema
    assert db.get_application_by_id(owner_id, app_id)[1] == "Keep Co"
    assert query(test_db_path, "SELECT count(*) FROM users") == [(1,)]  # no legacy owner on a fresh database


def test_database_newer_than_the_app_is_refused(test_db_path):
    query(test_db_path, f"PRAGMA user_version = {db.SCHEMA_VERSION + 1}")
    with pytest.raises(db.MigrationError):
        db.init_db()


# --- Upgrading a single-user database ---------------------------------------------------------

def test_legacy_records_are_preserved_exactly_and_owned_by_the_configured_account(legacy_path):
    before = legacy_data(legacy_path)
    db.init_db(LEGACY_OWNER_SUB)

    assert user_version(legacy_path) == db.SCHEMA_VERSION
    assert legacy_data(legacy_path) == before  # every row and column, unchanged
    owners = query(legacy_path, "SELECT id, google_sub, email, name FROM users")
    assert len(owners) == 1 and owners[0][1:] == (LEGACY_OWNER_SUB, None, None)
    owner_id = owners[0][0]
    assert set(query(legacy_path, "SELECT user_id FROM applications")) == {(owner_id,)}
    assert set(query(legacy_path, "SELECT user_id FROM resume_versions")) == {(owner_id,)}
    assert query(legacy_path, "PRAGMA foreign_key_check") == []
    assert query(legacy_path, "PRAGMA integrity_check") == [("ok",)]


def test_migrated_schema_is_identical_to_a_fresh_schema(legacy_path, fresh_schema):
    db.init_db(LEGACY_OWNER_SUB)
    assert schema_of(legacy_path) == fresh_schema
    assert not [name for (_, name, _, _) in schema_of(legacy_path) if name.startswith("legacy_")]


def test_legacy_owner_signs_in_and_sees_their_records(legacy_path):
    db.init_db(LEGACY_OWNER_SUB)
    owner_id = db.get_or_create_user(LEGACY_OWNER_SUB, "owner@example.com", "Legacy Owner")

    assert query(legacy_path, "SELECT count(*) FROM users") == [(1,)]  # the migrated user, not a new one
    assert {r[0] for r in db.get_all_applications(owner_id)} == {LEGACY_IDS["app_a"], LEGACY_IDS["app_b"]}
    assert db.get_application_by_id(owner_id, LEGACY_IDS["app_a"])[10] == LEGACY_IDS["resume"]
    assert [r[0] for r in db.get_interviews_by_application_id(owner_id, LEGACY_IDS["app_a"])] == [LEGACY_IDS["a_round1"]]
    assert [q[0] for q in db.get_questions_by_interview_id(owner_id, LEGACY_IDS["a_round1"])] == [
        LEGACY_IDS["a1_question"]]
    assert [r[0] for r in db.get_resume_versions(owner_id)] == [LEGACY_IDS["resume"]]
    # And keeps working normally afterwards.
    db.create_interview(owner_id, LEGACY_IDS["app_b"], 1, 1)


def test_legacy_records_are_not_given_to_whoever_signs_in_first(legacy_path):
    db.init_db(LEGACY_OWNER_SUB)
    first_visitor = db.get_or_create_user(OTHER_USER["sub"], OTHER_USER["email"], OTHER_USER["name"])
    assert db.get_all_applications(first_visitor) == []
    assert db.get_application_by_id(first_visitor, LEGACY_IDS["app_a"]) is None
    assert db.get_resume_versions(first_visitor) == []
    with pytest.raises(db.NotFoundError):
        db.create_interview(first_visitor, LEGACY_IDS["app_a"], 2, 1)
    with pytest.raises(db.NotFoundError):
        db.set_application_resume_version(first_visitor, db.create_application(first_visitor, "X", "Y"),
                                          LEGACY_IDS["resume"])


def test_backup_is_written_before_migrating(legacy_path):
    before = legacy_data(legacy_path)
    db.init_db(LEGACY_OWNER_SUB)
    [backup] = backups(legacy_path)
    assert user_version(backup) == 0
    assert legacy_data(backup) == before
    assert "users" not in {row[0] for row in query(backup, "SELECT name FROM sqlite_master")}


def test_migration_is_idempotent(legacy_path):
    db.init_db(LEGACY_OWNER_SUB)
    after_first = schema_of(legacy_path), legacy_data(legacy_path), query(legacy_path, "SELECT * FROM users")
    for owner in [LEGACY_OWNER_SUB, None, "a-different-owner"]:
        db.init_db(owner)
    assert (schema_of(legacy_path), legacy_data(legacy_path), query(legacy_path, "SELECT * FROM users")) == after_first
    assert len(backups(legacy_path)) == 1


@pytest.mark.parametrize("owner", [None, "", "   ", " padded ", "x" * 256])
def test_migration_without_a_valid_owner_stops_and_changes_nothing(legacy_path, owner):
    file_before = legacy_path.read_bytes()
    with pytest.raises(db.MigrationError, match="allowed_google_sub"):
        db.init_db(owner)
    assert legacy_path.read_bytes() == file_before
    assert user_version(legacy_path) == 0
    assert backups(legacy_path) == []


def test_empty_legacy_database_migrates_without_an_owner(test_db_path, monkeypatch, fresh_schema):
    create_legacy_db(test_db_path, with_data=False)
    monkeypatch.setattr(db, "DB_PATH", test_db_path)
    db.init_db(None)
    assert schema_of(test_db_path) == fresh_schema
    assert query(test_db_path, "SELECT count(*) FROM users") == [(0,)]
    assert backups(test_db_path) == []  # nothing to back up


def test_failure_mid_migration_rolls_everything_back(legacy_path, monkeypatch):
    schema_before, data_before = schema_of(legacy_path), legacy_data(legacy_path)

    def fail():  # db._now is first called after the legacy tables were renamed and the new ones created
        raise RuntimeError("simulated crash during migration")
    real_now = db._now
    monkeypatch.setattr(db, "_now", fail)

    with pytest.raises(RuntimeError, match="simulated crash"):
        db.init_db(LEGACY_OWNER_SUB)
    assert schema_of(legacy_path) == schema_before
    assert legacy_data(legacy_path) == data_before
    assert user_version(legacy_path) == 0

    monkeypatch.setattr(db, "_now", real_now)  # the next start-up completes the migration normally
    db.init_db(LEGACY_OWNER_SUB)
    assert legacy_data(legacy_path) == data_before and user_version(legacy_path) == db.SCHEMA_VERSION


def test_legacy_rows_that_break_foreign_keys_abort_the_migration(legacy_path):
    conn = sqlite3.connect(legacy_path)  # foreign keys off, as a buggy older version might have written
    conn.execute("INSERT INTO interviews (id, application_id) VALUES ('orphan', 'missing-application')")
    conn.commit()
    conn.close()
    schema_before, data_before = schema_of(legacy_path), legacy_data(legacy_path)

    with pytest.raises(db.MigrationError, match="Foreign key"):
        db.init_db(LEGACY_OWNER_SUB)
    assert (schema_of(legacy_path), legacy_data(legacy_path)) == (schema_before, data_before)


def test_legacy_columns_unknown_to_the_new_schema_abort_the_migration(legacy_path):
    query(legacy_path, "ALTER TABLE applications ADD COLUMN salary TEXT")
    with pytest.raises(db.MigrationError, match="salary"):
        db.init_db(LEGACY_OWNER_SUB)
    assert user_version(legacy_path) == 0
    assert "salary" in [c[1] for c in query(legacy_path, "PRAGMA table_info(applications)")]


def test_concurrent_start_ups_migrate_exactly_once(legacy_path):
    data_before = legacy_data(legacy_path)
    thread_count = 8
    barrier = threading.Barrier(thread_count)
    errors = []

    def start_up():
        try:
            barrier.wait()
            db.init_db(LEGACY_OWNER_SUB)
        except Exception as error:  # collected and asserted below
            errors.append(error)

    threads = [threading.Thread(target=start_up) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert legacy_data(legacy_path) == data_before
    assert query(legacy_path, "SELECT count(*) FROM users") == [(1,)]
    assert len(backups(legacy_path)) == 1


def test_legacy_schema_fixture_matches_the_original_schema_file():
    """Guard: the legacy fixture must stay the exact schema the single-user version shipped."""
    assert "user_id" not in LEGACY_SCHEMA_SQL and "users" not in LEGACY_SCHEMA_SQL
    assert LEGACY_SCHEMA_SQL.count("CREATE TABLE") == 4
