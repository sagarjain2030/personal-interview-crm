"""AppTest: Questions page (Step 7)."""
import pytest

import db
from app_helpers import by_label, click, open_app, texts

QUESTION = "Interview Question"
MY_ANSWER = "My Answer / Apparent Answer (optional)"
BETTER_ANSWER = "Better Answer (optional)"


def select(at, label, value):
    by_label(at.selectbox, label).set_value(value).run()
    assert not at.exception


def open_round(application_id, interview_id):
    """Open the Questions page with an explicit application and interview round selected.
    (The default selection is the newest application, so tests always choose explicitly.)"""
    at = open_app("Questions")
    select(at, "Select Application", application_id)
    select(at, "Select Interview Round", interview_id)
    return at


def save_question(at, question, my_answer="", better_answer=""):
    by_label(at.text_area, QUESTION).input(question)
    by_label(at.text_area, MY_ANSWER).input(my_answer)
    by_label(at.text_area, BETTER_ANSWER).input(better_answer)
    return click(at, "Save Question")


def test_no_applications_state():
    at = open_app("Questions")
    assert "No saved applications yet. Add one on the Jobs page first." in texts(at.info)


def test_application_without_interviews_shows_guidance():
    db.create_application("Acme", "Dev")
    at = open_app("Questions")
    assert "No interviews recorded for this application yet. Add one on the Interviews page first." in texts(at.info)
    assert len(at.selectbox) == 1  # only the application dropdown
    assert len(at.text_area) == 0


def test_interview_without_questions_shows_empty_state(seeded):
    at = open_app("Questions")
    select(at, "Select Application", seeded["app_a"])
    select(at, "Select Interview Round", seeded["a_round2"])
    assert "No questions recorded for this interview yet." in texts(at.info)


def test_form_inputs_exist(seeded):
    at = open_app("Questions")
    for label in (QUESTION, MY_ANSWER, BETTER_ANSWER):
        by_label(at.text_area, label)
    by_label(at.button, "Save Question")


def test_dropdowns_use_uuids_and_list_only_selected_applications_rounds(seeded):
    at = open_app("Questions")
    select(at, "Select Application", seeded["app_a"])
    assert by_label(at.selectbox, "Select Application").value == seeded["app_a"]
    rounds = by_label(at.selectbox, "Select Interview Round")
    assert rounds.options == ["Round 1 — Recruiter / HR Screening", "Round 2 — Technical Interview"]
    assert rounds.value == seeded["a_round1"]

    select(at, "Select Application", seeded["app_b"])
    rounds = by_label(at.selectbox, "Select Interview Round")
    assert rounds.options == ["Round 1 — Hiring Manager Interview"]
    assert rounds.value == seeded["b_round1"]


def test_duplicate_round_labels_are_distinguishable():
    app_id = db.create_application("Acme", "Dev")
    first = db.create_interview(app_id, 2, 2)
    second = db.create_interview(app_id, 2, 2)
    at = open_app("Questions")
    options = by_label(at.selectbox, "Select Interview Round").options
    assert sorted(options) == sorted([f"Round 2 — Technical Interview ({first[:8]})",
                                      f"Round 2 — Technical Interview ({second[:8]})"])
    select(at, "Select Interview Round", second)
    save_question(at, "For the second duplicate round")
    assert [q[1] for q in db.get_questions_by_interview_id(second)] == ["For the second duplicate round"]
    assert db.get_questions_by_interview_id(first) == []


@pytest.mark.parametrize("blank", ["", "   ", "\n\t  \n"])
def test_empty_or_whitespace_question_rejected(seeded, fetch_rows, blank):
    at = open_app("Questions")
    save_question(at, blank, my_answer="An answer without a question")
    assert "Interview question is required." in texts(at.error)
    assert fetch_rows("SELECT count(*) FROM interview_questions") == [(1,)]  # only the seeded one


def test_valid_question_saved_and_displayed(seeded, fetch_rows):
    at = open_round(seeded["app_a"], seeded["a_round2"])
    save_question(at, "  Explain the GIL.\nWhy does it matter?  ",
                  "A lock in CPython.\nOnly one thread runs bytecode.",
                  "  Use multiprocessing for CPU-bound work.  ")

    assert "Question saved for Round 2 — Technical Interview." in texts(at.success)
    rows = fetch_rows("SELECT interview_id, question, apparent_answer, better_answer FROM interview_questions "
                      "WHERE interview_id=?", (seeded["a_round2"],))
    assert rows == [(seeded["a_round2"], "Explain the GIL.\nWhy does it matter?",
                     "A lock in CPython.\nOnly one thread runs bytecode.",
                     "Use multiprocessing for CPU-bound work.")]
    assert texts(at.text) == ["Explain the GIL.\nWhy does it matter?",
                              "A lock in CPython.\nOnly one thread runs bytecode.",
                              "Use multiprocessing for CPU-bound work."]


def test_blank_answers_stored_as_null_and_shown_as_not_recorded(seeded, fetch_rows):
    at = open_round(seeded["app_a"], seeded["a_round2"])
    save_question(at, "Question without answers", "   ", "")
    assert fetch_rows("SELECT apparent_answer, better_answer FROM interview_questions WHERE question=?",
                      ("Question without answers",)) == [(None, None)]
    assert texts(at.text) == ["Question without answers", "Not recorded", "Not recorded"]


def test_questions_listed_in_insertion_order_with_numbers(seeded):
    at = open_round(seeded["app_a"], seeded["a_round1"])
    save_question(at, "Second question")
    save_question(at, "Third question")
    shown = texts(at.text)
    assert shown[0::3] == ["What is a Python decorator?", "Second question", "Third question"]
    assert [m for m in texts(at.markdown) if m.startswith("**Question")] == [
        "**Question 1**", "**Question 2**", "**Question 3**"]


def test_switching_interviews_and_applications_never_mixes_questions(seeded):
    at = open_app("Questions")
    select(at, "Select Application", seeded["app_a"])
    assert "What is a Python decorator?" in texts(at.text)

    select(at, "Select Interview Round", seeded["a_round2"])
    assert "What is a Python decorator?" not in texts(at.text)
    save_question(at, "Round two question")

    select(at, "Select Interview Round", seeded["a_round1"])
    assert "Round two question" not in texts(at.text)
    assert "What is a Python decorator?" in texts(at.text)

    select(at, "Select Application", seeded["app_b"])
    assert texts(at.text) == []
    assert "No questions recorded for this interview yet." in texts(at.info)


def test_special_characters_are_displayed_literally(seeded):
    question = "What does **kwargs do? <script>alert(1)</script> & 'quotes' — ✓"
    at = open_app("Questions")
    save_question(at, question, "# not a heading\n- not a list")
    assert question in texts(at.text)
    assert "# not a heading\n- not a list" in texts(at.text)


def test_long_question_text_is_saved_completely(seeded, fetch_rows):
    long_question = "Describe the architecture. " * 300
    at = open_app("Questions")
    save_question(at, long_question)
    stored = fetch_rows("SELECT question FROM interview_questions WHERE question LIKE 'Describe%'")
    assert stored == [(long_question.strip(),)]


def test_questions_persist_in_a_fresh_session(seeded):
    at = open_round(seeded["app_a"], seeded["a_round1"])
    save_question(at, "Persistent question")
    fresh = open_round(seeded["app_a"], seeded["a_round1"])
    assert "Persistent question" in texts(fresh.text)


def test_saving_question_does_not_change_interview_or_application(seeded, fetch_rows):
    before = fetch_rows("SELECT * FROM interviews"), fetch_rows("SELECT * FROM applications")
    at = open_app("Questions")
    save_question(at, "Side-effect check")
    assert (fetch_rows("SELECT * FROM interviews"), fetch_rows("SELECT * FROM applications")) == before
