"""Adversarial multi-user tests: User A must never read, change or attach to User B's records.

Every test calls db.py directly with another user's record IDs, bypassing the UI's dropdowns,
as an attacker who learned (or guessed) a UUID would.
"""
import inspect
import sqlite3
import uuid

import pytest

import db


@pytest.fixture
def victim(other_user_id):
    """OTHER_USER's records: an application with a resume, an interview round and a question."""
    resume = db.create_resume_version(other_user_id, "Victim CV", "private notes")
    app = db.create_application(other_user_id, "Victim Co", "Secret Role", "private JD", notes="private")
    db.set_application_resume_version(other_user_id, app, resume)
    interview = db.create_interview(other_user_id, app, 1, 2)
    question = db.create_interview_question(other_user_id, interview, "Victim question", "victim answer")
    return {"user": other_user_id, "resume": resume, "app": app, "interview": interview, "question": question}


@pytest.fixture
def attacker(owner_id):
    """TEST_USER, with their own application, interview and resume."""
    app = db.create_application(owner_id, "Attacker Co", "Role")
    return {"user": owner_id, "app": app, "interview": db.create_interview(owner_id, app, 1, 1),
            "resume": db.create_resume_version(owner_id, "Attacker CV")}


@pytest.fixture
def snapshot(fetch_rows):
    """All rows of every table, to prove a denied operation changed nothing."""
    def _snapshot():
        return {t: fetch_rows(f"SELECT * FROM {t} ORDER BY rowid")
                for t in ["users", "resume_versions", "applications", "interviews", "interview_questions"]}
    return _snapshot


# --- Reads ------------------------------------------------------------------------------------

def test_application_list_contains_only_own_applications(victim, attacker):
    assert [r[0] for r in db.get_all_applications(attacker["user"])] == [attacker["app"]]
    assert [r[0] for r in db.get_all_applications(victim["user"])] == [victim["app"]]


def test_cannot_read_another_users_application_by_id(victim, attacker):
    assert db.get_application_by_id(attacker["user"], victim["app"]) is None
    assert db.get_application_by_id(victim["user"], victim["app"])[1] == "Victim Co"


def test_cannot_list_interviews_of_another_users_application(victim, attacker):
    assert db.get_interviews_by_application_id(attacker["user"], victim["app"]) == []
    assert len(db.get_interviews_by_application_id(victim["user"], victim["app"])) == 1


def test_cannot_list_questions_of_another_users_interview(victim, attacker):
    assert db.get_questions_by_interview_id(attacker["user"], victim["interview"]) == []
    assert db.get_questions_by_interview_id(victim["user"], victim["interview"])[0][1] == "Victim question"


def test_resume_list_contains_only_own_resumes(victim, attacker):
    assert [r[0] for r in db.get_resume_versions(attacker["user"])] == [attacker["resume"]]
    assert [r[0] for r in db.get_resume_versions(victim["user"])] == [victim["resume"]]


def test_unknown_or_forged_user_ids_see_nothing(victim):
    for forged in [str(uuid.uuid4()), None, "", victim["app"], "x' OR '1'='1", "1 OR 1=1; --"]:
        assert db.get_all_applications(forged) == []
        assert db.get_application_by_id(forged, victim["app"]) is None
        assert db.get_interviews_by_application_id(forged, victim["app"]) == []
        assert db.get_questions_by_interview_id(forged, victim["interview"]) == []
        assert db.get_resume_versions(forged) == []


@pytest.mark.parametrize("injected", ["' OR '1'='1", "x' OR 1=1 --", "%", "*", "') OR ('a'='a"])
def test_sql_injection_in_record_ids_finds_nothing(victim, attacker, injected):
    assert db.get_application_by_id(attacker["user"], injected) is None
    assert db.get_interviews_by_application_id(attacker["user"], injected) == []
    assert db.get_questions_by_interview_id(attacker["user"], injected) == []
    with pytest.raises(db.NotFoundError):
        db.update_application_status(attacker["user"], injected, 4)


# --- Writes -----------------------------------------------------------------------------------

@pytest.mark.parametrize("operation", [
    lambda a, v: db.update_application_details(a["user"], v["app"], "Hacked", "Hacked", None, None, None, None),
    lambda a, v: db.update_application_status(a["user"], v["app"], 6),
    lambda a, v: db.update_application_priority(a["user"], v["app"], 1),
    lambda a, v: db.create_interview(a["user"], v["app"], 9, 1),
    lambda a, v: db.create_interview_question(a["user"], v["interview"], "Injected question"),
    lambda a, v: db.set_application_resume_version(a["user"], v["app"], None),
    lambda a, v: db.set_application_resume_version(a["user"], v["app"], a["resume"]),
    lambda a, v: db.set_application_resume_version(a["user"], a["app"], v["resume"]),
    lambda a, v: db.set_application_resume_version(a["user"], v["app"], v["resume"]),
], ids=["edit-details", "status", "priority", "add-interview", "add-question", "unlink-resume",
        "attach-own-resume-to-victim-app", "attach-victim-resume-to-own-app", "relink-victim-resume"])
def test_cross_user_writes_are_denied_and_change_nothing(victim, attacker, snapshot, operation):
    before = snapshot()
    with pytest.raises(db.NotFoundError):
        operation(attacker, victim)
    assert snapshot() == before


def test_denial_does_not_reveal_whether_the_record_exists(victim, attacker):
    """Another user's record and a non-existent record produce the identical error."""
    with pytest.raises(db.NotFoundError) as foreign:
        db.update_application_status(attacker["user"], victim["app"], 1)
    with pytest.raises(db.NotFoundError) as missing:
        db.update_application_status(attacker["user"], str(uuid.uuid4()), 1)
    assert str(foreign.value) == str(missing.value)


def test_owner_can_still_modify_own_records(victim, attacker):
    db.update_application_status(attacker["user"], attacker["app"], 1)
    db.set_application_resume_version(attacker["user"], attacker["app"], attacker["resume"])
    record = db.get_application_by_id(attacker["user"], attacker["app"])
    assert (record[9], record[10]) == (1, attacker["resume"])
    db.set_application_resume_version(attacker["user"], attacker["app"], None)
    assert db.get_application_by_id(attacker["user"], attacker["app"])[10] is None


def test_new_records_are_owned_by_the_creating_user(attacker, fetch_rows):
    assert fetch_rows("SELECT user_id FROM applications WHERE id=?", (attacker["app"],)) == [(attacker["user"],)]
    assert fetch_rows("SELECT user_id FROM resume_versions WHERE id=?", (attacker["resume"],)) == [(attacker["user"],)]


def test_creating_records_for_a_nonexistent_user_fails(fetch_rows):
    for forged in [str(uuid.uuid4()), None]:
        with pytest.raises(sqlite3.IntegrityError):
            db.create_application(forged, "Ghost Co", "Role")
        with pytest.raises(sqlite3.IntegrityError):
            db.create_resume_version(forged, "Ghost CV")
    assert fetch_rows("SELECT count(*) FROM applications") == [(0,)]


def test_application_id_returned_to_one_user_is_useless_to_another(owner_id, other_user_id):
    app_id = db.create_application(owner_id, "Mine", "Role")
    with pytest.raises(db.NotFoundError):
        db.create_interview(other_user_id, app_id, 1, 1)
    assert db.get_application_by_id(other_user_id, app_id) is None


# --- Defence in depth: the schema itself rejects cross-user and dangling references -----------

def raw_execute(path, statement, params):
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            conn.execute(statement, params)
    finally:
        conn.close()


def test_schema_rejects_linking_another_users_resume(victim, attacker, test_db_path, snapshot):
    before = snapshot()
    with pytest.raises(sqlite3.IntegrityError):
        raw_execute(test_db_path, "UPDATE applications SET resume_version_id=? WHERE id=?",
                    (victim["resume"], attacker["app"]))
    with pytest.raises(sqlite3.IntegrityError):
        raw_execute(test_db_path, "INSERT INTO applications (id, user_id, company, role, created_at, "
                    "resume_version_id) VALUES (?, ?, 'X', 'Y', '2026', ?)",
                    (str(uuid.uuid4()), attacker["user"], victim["resume"]))
    assert snapshot() == before


@pytest.mark.parametrize("statement", [
    "INSERT INTO applications (id, user_id, company, role, created_at) VALUES (?, 'no-such-user', 'X', 'Y', '2026')",
    "INSERT INTO interviews (id, application_id) VALUES (?, 'no-such-application')",
    "INSERT INTO interview_questions (id, interview_id, question) VALUES (?, 'no-such-interview', 'Q')",
    "INSERT INTO resume_versions (id, user_id, name, created_at) VALUES (?, 'no-such-user', 'CV', '2026')",
    "INSERT INTO applications (id, user_id, company, role, created_at) VALUES (?, NULL, 'X', 'Y', '2026')",
])
def test_schema_rejects_dangling_or_ownerless_records(test_db_path, statement):
    with pytest.raises(sqlite3.IntegrityError):
        raw_execute(test_db_path, statement, (str(uuid.uuid4()),))


# --- Guard for future changes -----------------------------------------------------------------

def test_every_record_function_requires_the_user_id_first():
    """A new data-access function that forgets the owner would silently break isolation."""
    not_user_scoped = {"get_connection", "init_db", "validate_google_sub", "get_or_create_user"}
    record_functions = [name for name, obj in vars(db).items()
                        if inspect.isfunction(obj) and obj.__module__ == "db"
                        and not name.startswith("_") and name not in not_user_scoped]
    assert len(record_functions) >= 13
    for name in record_functions:
        first = next(iter(inspect.signature(getattr(db, name)).parameters))
        assert first == "user_id", name
