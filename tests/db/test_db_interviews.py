"""Database tests for interview rounds (Step 6)."""
import sqlite3
import uuid

import pytest

import db


def test_create_interview_links_to_application(owner_id, fetch_rows):
    app_id = db.create_application(owner_id, "Acme", "Dev")
    interview_id = db.create_interview(owner_id, app_id, 1, 2)

    uuid.UUID(interview_id)
    rows = fetch_rows("SELECT application_id, round_number, round_type, result FROM interviews WHERE id=?",
                      (interview_id,))
    assert rows == [(app_id, 1, 2, 0)]


def test_round_type_stored_as_integer(owner_id, fetch_rows):
    app_id = db.create_application(owner_id, "Acme", "Dev")
    interview_id = db.create_interview(owner_id, app_id, 1, 4)
    assert fetch_rows("SELECT typeof(round_type), typeof(round_number) FROM interviews WHERE id=?",
                      (interview_id,)) == [("integer", "integer")]


def test_result_defaults_to_scheduled(owner_id):
    app_id = db.create_application(owner_id, "Acme", "Dev")
    db.create_interview(owner_id, app_id, 1, 1)
    assert db.get_interviews_by_application_id(owner_id, app_id)[0][3] == 0  # 0 = Scheduled


def test_other_columns_use_schema_defaults(owner_id, fetch_rows):
    app_id = db.create_application(owner_id, "Acme", "Dev")
    interview_id = db.create_interview(owner_id, app_id, 1, 1)
    rows = fetch_rows("SELECT interview_date, interviewer, confidence, notes, ai_analysis_status, ai_analysis "
                      "FROM interviews WHERE id=?", (interview_id,))
    assert rows == [(None, None, 0, None, 0, None)]


def test_interview_uuids_are_unique(owner_id):
    app_id = db.create_application(owner_id, "Acme", "Dev")
    ids = {db.create_interview(owner_id, app_id, n, 1) for n in range(1, 6)}
    assert len(ids) == 5


def test_multiple_rounds_returned_in_round_number_order(owner_id):
    app_id = db.create_application(owner_id, "Acme", "Dev")
    third = db.create_interview(owner_id, app_id, 3, 3)
    first = db.create_interview(owner_id, app_id, 1, 1)
    second = db.create_interview(owner_id, app_id, 2, 2)

    records = db.get_interviews_by_application_id(owner_id, app_id)
    assert [r[0] for r in records] == [first, second, third]
    assert [r[1] for r in records] == [1, 2, 3]


def test_duplicate_round_numbers_are_allowed(owner_id):
    # Not prevented by schema or helper; documented limitation.
    app_id = db.create_application(owner_id, "Acme", "Dev")
    db.create_interview(owner_id, app_id, 2, 2)
    db.create_interview(owner_id, app_id, 2, 2)
    assert len(db.get_interviews_by_application_id(owner_id, app_id)) == 2


def test_rounds_from_different_applications_do_not_mix(owner_id, seeded):
    a_ids = {r[0] for r in db.get_interviews_by_application_id(owner_id, seeded["app_a"])}
    b_ids = {r[0] for r in db.get_interviews_by_application_id(owner_id, seeded["app_b"])}
    assert a_ids == {seeded["a_round1"], seeded["a_round2"]}
    assert b_ids == {seeded["b_round1"]}


def test_no_interviews_returns_empty_list(owner_id):
    app_id = db.create_application(owner_id, "Acme", "Dev")
    assert db.get_interviews_by_application_id(owner_id, app_id) == []


def test_unknown_application_id_rejected(owner_id, fetch_rows):
    # The ownership check rejects it before the foreign key would (see test_db_security.py for the FK itself).
    with pytest.raises(db.NotFoundError):
        db.create_interview(owner_id, str(uuid.uuid4()), 1, 1)
    assert fetch_rows("SELECT count(*) FROM interviews") == [(0,)]


@pytest.mark.parametrize("round_number, round_type", [(0, 1), (-1, 1), (1, -1), (1, 5)])
def test_schema_rejects_invalid_round_number_or_type(owner_id, round_number, round_type, fetch_rows):
    app_id = db.create_application(owner_id, "Acme", "Dev")
    with pytest.raises(sqlite3.IntegrityError):
        db.create_interview(owner_id, app_id, round_number, round_type)
    assert fetch_rows("SELECT count(*) FROM interviews") == [(0,)]


def test_adding_a_round_does_not_change_application(owner_id):
    app_id = db.create_application(owner_id, "Acme", "Dev")
    db.update_application_status(owner_id, app_id, 0)
    before = db.get_application_by_id(owner_id, app_id)

    db.create_interview(owner_id, app_id, 1, 1)

    assert db.get_application_by_id(owner_id, app_id) == before
