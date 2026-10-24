"""Database tests for interview questions and answers (Step 7)."""
import sqlite3
import uuid

import pytest

import db


@pytest.fixture
def interview_id(owner_id):
    app_id = db.create_application(owner_id, "Acme", "Dev")
    return db.create_interview(owner_id, app_id, 1, 2)


def test_create_question_with_answers(owner_id, interview_id, fetch_rows):
    question_id = db.create_interview_question(owner_id, interview_id, "What is the GIL?", "A lock.", "A mutex in CPython...")

    uuid.UUID(question_id)
    rows = fetch_rows("SELECT interview_id, question, apparent_answer, better_answer "
                      "FROM interview_questions WHERE id=?", (question_id,))
    assert rows == [(interview_id, "What is the GIL?", "A lock.", "A mutex in CPython...")]


def test_optional_answers_can_be_null(owner_id, interview_id):
    db.create_interview_question(owner_id, interview_id, "Question only")
    assert db.get_questions_by_interview_id(owner_id, interview_id)[0][2:] == (None, None)


def test_new_question_defaults(owner_id, interview_id, fetch_rows):
    question_id = db.create_interview_question(owner_id, interview_id, "Q")
    rows = fetch_rows("SELECT topic, subtopic, missing_concept, priority FROM interview_questions WHERE id=?",
                      (question_id,))
    assert rows == [(None, None, None, 2)]


def test_question_uuids_are_unique(owner_id, interview_id):
    ids = {db.create_interview_question(owner_id, interview_id, f"Q{n}") for n in range(5)}
    assert len(ids) == 5


def test_questions_returned_in_insertion_order(owner_id, interview_id):
    texts = ["Zebra question", "Apple question", "Mango question"]
    ids = [db.create_interview_question(owner_id, interview_id, t) for t in texts]

    records = db.get_questions_by_interview_id(owner_id, interview_id)
    assert [r[0] for r in records] == ids
    assert [r[1] for r in records] == texts


def test_questions_from_different_interviews_do_not_mix(owner_id, seeded):
    db.create_interview_question(owner_id, seeded["a_round2"], "Round 2 only")

    round1 = [r[1] for r in db.get_questions_by_interview_id(owner_id, seeded["a_round1"])]
    round2 = [r[1] for r in db.get_questions_by_interview_id(owner_id, seeded["a_round2"])]
    other_app = db.get_questions_by_interview_id(owner_id, seeded["b_round1"])

    assert round1 == ["What is a Python decorator?"]
    assert round2 == ["Round 2 only"]
    assert other_app == []


def test_no_questions_returns_empty_list(owner_id, interview_id):
    assert db.get_questions_by_interview_id(owner_id, interview_id) == []
    assert db.get_questions_by_interview_id(owner_id, str(uuid.uuid4())) == []


def test_unknown_interview_id_rejected(owner_id, fetch_rows):
    # The ownership check rejects it before the foreign key would (see test_db_security.py for the FK itself).
    with pytest.raises(db.NotFoundError):
        db.create_interview_question(owner_id, str(uuid.uuid4()), "Orphan question")
    assert fetch_rows("SELECT count(*) FROM interview_questions") == [(0,)]


def test_null_question_rejected_by_schema(owner_id, interview_id):
    # The schema enforces NOT NULL only; blank-string validation lives in the Streamlit page.
    with pytest.raises(sqlite3.IntegrityError):
        db.create_interview_question(owner_id, interview_id, None)


def test_long_multiline_and_special_text_round_trip(owner_id, interview_id):
    question = "Explain *args/**kwargs & <generics>?\n" + "x" * 5000
    answer = "Line 1\n  indented line 2\n\tTabbed — ✓ 'quotes' \"double\""
    db.create_interview_question(owner_id, interview_id, question, answer, "# not a heading\n- not a list")

    record = db.get_questions_by_interview_id(owner_id, interview_id)[0]
    assert record[1:] == (question, answer, "# not a heading\n- not a list")


def test_adding_question_does_not_change_interview_or_application(owner_id, interview_id, fetch_rows):
    before = fetch_rows("SELECT * FROM interviews"), fetch_rows("SELECT * FROM applications")
    db.create_interview_question(owner_id, interview_id, "Q")
    assert (fetch_rows("SELECT * FROM interviews"), fetch_rows("SELECT * FROM applications")) == before
