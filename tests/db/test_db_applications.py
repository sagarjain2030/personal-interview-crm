"""Database tests for job applications (Steps 3–5)."""
import sqlite3
import uuid

import pytest

import db


def test_create_application_stores_company_role_and_defaults(fetch_rows):
    app_id = db.create_application("Acme Corp", "Python Developer")

    rows = fetch_rows("SELECT company, role, status, priority, created_at FROM applications WHERE id=?", (app_id,))
    assert len(rows) == 1
    company, role, status, priority, created_at = rows[0]
    assert (company, role) == ("Acme Corp", "Python Developer")
    assert status == 0  # Applied
    assert priority == 2  # Medium
    assert created_at


def test_each_application_gets_a_unique_uuid():
    ids = {db.create_application("Same Co", "Same Role") for _ in range(5)}
    assert len(ids) == 5
    for app_id in ids:
        uuid.UUID(app_id)  # raises ValueError if not a valid UUID


def test_optional_fields_are_saved(fetch_rows):
    app_id = db.create_application(
        "Acme", "Dev",
        raw_job_description="Line 1\nLine 2",
        jd_url="https://example.com/job",
        location="Remote",
        notes="Referral from Sam",
    )
    rows = fetch_rows("SELECT raw_job_description, jd_url, location, notes FROM applications WHERE id=?", (app_id,))
    assert rows == [("Line 1\nLine 2", "https://example.com/job", "Remote", "Referral from Sam")]


def test_optional_fields_default_to_null(fetch_rows):
    app_id = db.create_application("Acme", "Dev")
    rows = fetch_rows("SELECT raw_job_description, jd_url, location, notes FROM applications WHERE id=?", (app_id,))
    assert rows == [(None, None, None, None)]


def test_get_all_applications_returns_newest_first():
    first = db.create_application("First", "Role")
    second = db.create_application("Second", "Role")

    records = db.get_all_applications()
    assert [r[0] for r in records] == [second, first]
    assert records[0][1:4] == ("Second", "Role", 0)  # (id, company, role, status, created_at)


def test_get_all_applications_empty_database():
    assert db.get_all_applications() == []


def test_get_application_by_id():
    app_id = db.create_application("Acme", "Dev", location="Berlin")
    record = db.get_application_by_id(app_id)
    assert record[0] == app_id
    assert record[1:3] == ("Acme", "Dev")
    assert record[5] == "Berlin"
    assert db.get_application_by_id(str(uuid.uuid4())) is None


def test_update_details_changes_only_editable_fields():
    app_id = db.create_application("Old Co", "Old Role", "old jd", "old url", "old loc", "old notes")
    db.update_application_status(app_id, 1)
    db.update_application_priority(app_id, 3)
    before = db.get_application_by_id(app_id)

    db.update_application_details(app_id, "New Co", "New Role", "new jd", "new url", "new loc", "new notes")

    after = db.get_application_by_id(app_id)
    assert after[1:7] == ("New Co", "New Role", "new jd", "new url", "new loc", "new notes")
    assert after[0] == before[0]  # UUID preserved
    assert after[7] == before[7]  # created_at preserved
    assert after[9] == 1  # status unchanged
    assert after[11] == 3  # priority unchanged


def test_update_details_affects_only_selected_application():
    target = db.create_application("Target", "Role")
    other = db.create_application("Other", "Role")
    other_before = db.get_application_by_id(other)

    db.update_application_details(target, "Changed", "Role", None, None, None, None)

    assert db.get_application_by_id(other) == other_before


def test_status_update_affects_only_selected_application():
    target = db.create_application("Target", "Role")
    other = db.create_application("Other", "Role")

    db.update_application_status(target, 4)

    assert db.get_application_by_id(target)[9] == 4
    assert db.get_application_by_id(other)[9] == 0


def test_priority_update_affects_only_selected_application():
    target = db.create_application("Target", "Role")
    other = db.create_application("Other", "Role")

    db.update_application_priority(target, 1)

    assert db.get_application_by_id(target)[11] == 1
    assert db.get_application_by_id(other)[11] == 2


def test_status_and_priority_constraints_reject_out_of_range_values():
    app_id = db.create_application("Acme", "Dev")
    with pytest.raises(sqlite3.IntegrityError):
        db.update_application_status(app_id, 7)
    with pytest.raises(sqlite3.IntegrityError):
        db.update_application_priority(app_id, 0)
    record = db.get_application_by_id(app_id)
    assert (record[9], record[11]) == (0, 2)


def test_records_persist_in_a_new_connection(test_db_path):
    app_id = db.create_application("Persisted", "Role")
    conn = sqlite3.connect(test_db_path)
    try:
        assert conn.execute("SELECT company FROM applications WHERE id=?", (app_id,)).fetchone() == ("Persisted",)
    finally:
        conn.close()


def test_special_characters_round_trip():
    text = "O'Reilly & \"Sons\" — Ünïcödé 🚀 <b>; DROP TABLE applications; --"
    app_id = db.create_application(text, text, notes=text)
    record = db.get_application_by_id(app_id)
    assert record[1] == record[2] == record[6] == text
    assert len(db.get_all_applications()) == 1  # table intact, parameterized SQL
