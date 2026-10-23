"""Database tests for interview rounds (Step 6)."""
import sqlite3
import uuid

import pytest

import db


def test_create_interview_links_to_application(fetch_rows):
    app_id = db.create_application("Acme", "Dev")
    interview_id = db.create_interview(app_id, 1, 2)

    uuid.UUID(interview_id)
    rows = fetch_rows("SELECT application_id, round_number, round_type, result FROM interviews WHERE id=?",
                      (interview_id,))
    assert rows == [(app_id, 1, 2, 0)]


def test_round_type_stored_as_integer(fetch_rows):
    app_id = db.create_application("Acme", "Dev")
    interview_id = db.create_interview(app_id, 1, 4)
    assert fetch_rows("SELECT typeof(round_type), typeof(round_number) FROM interviews WHERE id=?",
                      (interview_id,)) == [("integer", "integer")]


def test_result_defaults_to_scheduled():
    app_id = db.create_application("Acme", "Dev")
    db.create_interview(app_id, 1, 1)
    assert db.get_interviews_by_application_id(app_id)[0][3] == 0  # 0 = Scheduled


def test_other_columns_use_schema_defaults(fetch_rows):
    app_id = db.create_application("Acme", "Dev")
    interview_id = db.create_interview(app_id, 1, 1)
    rows = fetch_rows("SELECT interview_date, interviewer, confidence, notes, ai_analysis_status, ai_analysis "
                      "FROM interviews WHERE id=?", (interview_id,))
    assert rows == [(None, None, 0, None, 0, None)]


def test_interview_uuids_are_unique():
    app_id = db.create_application("Acme", "Dev")
    ids = {db.create_interview(app_id, n, 1) for n in range(1, 6)}
    assert len(ids) == 5


def test_multiple_rounds_returned_in_round_number_order():
    app_id = db.create_application("Acme", "Dev")
    third = db.create_interview(app_id, 3, 3)
    first = db.create_interview(app_id, 1, 1)
    second = db.create_interview(app_id, 2, 2)

    records = db.get_interviews_by_application_id(app_id)
    assert [r[0] for r in records] == [first, second, third]
    assert [r[1] for r in records] == [1, 2, 3]


def test_duplicate_round_numbers_are_allowed():
    # Not prevented by schema or helper; documented limitation.
    app_id = db.create_application("Acme", "Dev")
    db.create_interview(app_id, 2, 2)
    db.create_interview(app_id, 2, 2)
    assert len(db.get_interviews_by_application_id(app_id)) == 2


def test_rounds_from_different_applications_do_not_mix(seeded):
    a_ids = {r[0] for r in db.get_interviews_by_application_id(seeded["app_a"])}
    b_ids = {r[0] for r in db.get_interviews_by_application_id(seeded["app_b"])}
    assert a_ids == {seeded["a_round1"], seeded["a_round2"]}
    assert b_ids == {seeded["b_round1"]}


def test_no_interviews_returns_empty_list():
    app_id = db.create_application("Acme", "Dev")
    assert db.get_interviews_by_application_id(app_id) == []


def test_unknown_application_id_rejected_by_foreign_key():
    with pytest.raises(sqlite3.IntegrityError):
        db.create_interview(str(uuid.uuid4()), 1, 1)


@pytest.mark.parametrize("round_number, round_type", [(0, 1), (-1, 1), (1, -1), (1, 5)])
def test_schema_rejects_invalid_round_number_or_type(round_number, round_type, fetch_rows):
    app_id = db.create_application("Acme", "Dev")
    with pytest.raises(sqlite3.IntegrityError):
        db.create_interview(app_id, round_number, round_type)
    assert fetch_rows("SELECT count(*) FROM interviews") == [(0,)]


def test_adding_a_round_does_not_change_application():
    app_id = db.create_application("Acme", "Dev")
    db.update_application_status(app_id, 0)
    before = db.get_application_by_id(app_id)

    db.create_interview(app_id, 1, 1)

    assert db.get_application_by_id(app_id) == before
