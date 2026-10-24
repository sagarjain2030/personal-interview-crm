"""AppTest: database failures are shown as messages instead of crashing the app.

Real failures (missing/corrupt database) are used where they can be triggered deterministically.
For failures that cannot be produced on demand (e.g. a locked database during a save), the single
db helper is replaced with one that raises sqlite3.OperationalError - the UI error handling is what
is under test there, not the helper itself.
"""
import sqlite3

import pytest

import db
from app_helpers import by_label, click, contains, open_app, run_main, texts


def raise_db_error(*args, **kwargs):
    raise sqlite3.OperationalError("database is locked (simulated)")


def test_fresh_database_is_initialised_from_schema(tmp_path, monkeypatch, fetch_rows):
    fresh_path = tmp_path / "brand_new" / "nested" / "interview_crm.db"
    monkeypatch.setattr(db, "DB_PATH", fresh_path)
    at = open_app()
    assert fresh_path.exists()
    assert "No saved applications yet." in texts(at.info)
    conn = sqlite3.connect(fresh_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"applications", "interviews", "interview_questions", "resume_versions"} <= tables


def test_corrupt_database_file_shows_error(tmp_path, monkeypatch):
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"this is not a sqlite database" * 100)
    monkeypatch.setattr(db, "DB_PATH", broken)
    at = run_main()
    assert not at.exception
    assert contains(at.error, "Failed to initialize the database")
    assert len(at.sidebar.radio) == 0  # app stopped before rendering pages
    assert all(str(tmp_path) not in message and "not a database" not in message for message in texts(at.error))


def test_unopenable_database_path_shows_error(tmp_path, monkeypatch):
    directory_instead_of_file = tmp_path / "a_directory.db"
    directory_instead_of_file.mkdir()
    monkeypatch.setattr(db, "DB_PATH", directory_instead_of_file)
    at = run_main()
    assert not at.exception
    assert contains(at.error, "Failed to initialize the database")
    assert all(str(tmp_path) not in message for message in texts(at.error))  # no server paths


@pytest.mark.parametrize("section", ["Jobs", "Interviews", "Questions"])
def test_loading_applications_failure_shows_error(seeded, monkeypatch, section):
    monkeypatch.setattr(db, "get_all_applications", raise_db_error)
    at = open_app(section)
    assert contains(at.error, "Failed to load applications")


@pytest.mark.parametrize("section", ["Interviews", "Questions"])
def test_loading_interviews_failure_shows_error(seeded, monkeypatch, section):
    monkeypatch.setattr(db, "get_interviews_by_application_id", raise_db_error)
    at = open_app(section)
    assert contains(at.error, "Failed to retrieve interviews")


def test_loading_questions_failure_shows_error(seeded, monkeypatch):
    monkeypatch.setattr(db, "get_questions_by_interview_id", raise_db_error)
    at = open_app("Questions")
    assert contains(at.error, "Failed to retrieve questions")


def test_save_application_failure_shows_error(monkeypatch):
    monkeypatch.setattr(db, "create_application", raise_db_error)
    at = open_app()
    by_label(at.text_input, "Company").input("Acme")
    by_label(at.text_input, "Role").input("Dev")
    click(at, "Save Application")
    assert contains(at.error, "Failed to save application")


def test_save_edits_failure_shows_error(seeded, monkeypatch):
    monkeypatch.setattr(db, "update_application_details", raise_db_error)
    at = open_app()
    click(at, "Save Edit Changes")
    assert contains(at.error, "Failed to save edited application")


def test_save_status_failure_shows_error(seeded, monkeypatch):
    monkeypatch.setattr(db, "update_application_status", raise_db_error)
    at = open_app()
    by_label(at.selectbox, "Select Status").set_value(3)
    click(at, "Save Changes")
    assert contains(at.error, "Failed to save application")


def test_missing_application_record_shows_error(seeded, monkeypatch):
    monkeypatch.setattr(db, "get_application_by_id", lambda user_id, application_id: None)
    at = open_app()
    assert "The selected application could not be loaded." in texts(at.error)


def test_save_interview_failure_shows_error(seeded, monkeypatch):
    monkeypatch.setattr(db, "create_interview", raise_db_error)
    at = open_app("Interviews")
    click(at, "Save Interview")
    assert contains(at.error, "Failed to save interview")


def test_save_question_failure_shows_error(seeded, monkeypatch, fetch_rows):
    monkeypatch.setattr(db, "create_interview_question", raise_db_error)
    at = open_app("Questions")
    by_label(at.text_area, "Interview Question").input("Will fail")
    click(at, "Save Question")
    assert contains(at.error, "Failed to save question")
    assert fetch_rows("SELECT count(*) FROM interview_questions WHERE question='Will fail'") == [(0,)]


def test_raw_database_error_details_are_not_shown(seeded, monkeypatch):
    monkeypatch.setattr(db, "create_interview", raise_db_error)
    at = open_app("Interviews")
    click(at, "Save Interview")
    assert texts(at.error) == ["Failed to save interview."]
    assert not contains(at.error, "simulated")


def test_loading_selected_application_failure_shows_error(seeded, monkeypatch):
    monkeypatch.setattr(db, "get_application_by_id", raise_db_error)
    at = open_app()
    assert texts(at.error) == ["Failed to load the selected application."]


@pytest.mark.parametrize("helper, section, action", [
    ("update_application_details", "Jobs", "Save Edit Changes"),
    ("update_application_status", "Jobs", "Save Changes"),
    ("create_interview", "Interviews", "Save Interview"),
    ("create_interview_question", "Questions", "Save Question"),
])
def test_record_that_disappeared_or_is_not_owned_shows_not_found(seeded, monkeypatch, helper, section, action):
    """If the data layer denies a write (record gone or owned by someone else), nothing leaks and nothing is saved."""
    def deny(*args, **kwargs):
        raise db.NotFoundError("Application not found.")
    monkeypatch.setattr(db, helper, deny)
    at = open_app(section)
    if section == "Jobs" and action == "Save Changes":
        by_label(at.selectbox, "Select Status").set_value(3)
    if section == "Questions":
        by_label(at.text_area, "Interview Question").input("Q")
    click(at, action)
    assert texts(at.error) == ["The selected record could not be found."]
    assert not at.success


def test_too_long_input_is_rejected_with_a_clear_message(fetch_rows):
    at = open_app()
    by_label(at.text_input, "Company").input("C" * 201)
    by_label(at.text_input, "Role").input("Dev")
    click(at, "Save Application")
    assert texts(at.error) == ["Company must be at most 200 characters."]
    assert fetch_rows("SELECT count(*) FROM applications") == [(0,)]
