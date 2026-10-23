"""UI Tests 5, 6 & 7 — interview questions, optional answers and record isolation in a real browser."""
import pytest
from playwright.sync_api import expect

import db
from ui_helpers import (button, choose, dropdown, dropdown_options, expect_no_app_errors, open_section,
                        refresh)

pytestmark = pytest.mark.e2e


def save_question_via_ui(page, question, my_answer="", better_answer=""):
    page.get_by_label("Interview Question", exact=True).fill(question)
    page.get_by_label("My Answer / Apparent Answer (optional)", exact=True).fill(my_answer)
    page.get_by_label("Better Answer (optional)", exact=True).fill(better_answer)
    button(page, "Save Question").click()
    expect(page.get_by_text("Question saved for")).to_be_visible()
    expect(page.get_by_text(question.strip().splitlines()[0])).to_be_visible()


def open_round(page, application_label, round_label):
    open_section(page, "Questions")
    choose(page, "Select Application", application_label)
    choose(page, "Select Interview Round", round_label)


@pytest.fixture
def two_rounds():
    app_id = db.create_application("Questions Co", "Python Developer")
    return {"app": app_id,
            "round1": db.create_interview(app_id, 1, 1),
            "round2": db.create_interview(app_id, 2, 2)}


def test_create_question_with_multiline_answers(app, two_rounds):
    refresh(app)
    open_round(app, "Questions Co - Python Developer", "Round 1 — Recruiter / HR Screening")
    expect(app.get_by_text("No questions recorded for this interview yet.")).to_be_visible()

    save_question_via_ui(app, "Why do you want to join us?\nWhat do you know about the team?",
                         "I like the product.\nI read the engineering blog.",
                         "Mention specific projects\nand link them to my experience.")

    expect(app.get_by_text("Question 1", exact=True)).to_be_visible()
    # Multiline text keeps its line breaks in the rendered page.
    assert app.get_by_text("Why do you want to join us?").inner_text() == \
        "Why do you want to join us?\nWhat do you know about the team?"
    assert app.get_by_text("I like the product.").inner_text() == "I like the product.\nI read the engineering blog."
    assert app.get_by_text("Mention specific projects").inner_text() == \
        "Mention specific projects\nand link them to my experience."
    expect(app.get_by_label("Interview Question", exact=True)).to_have_value("")  # form cleared

    stored = db.get_questions_by_interview_id(two_rounds["round1"])
    assert [q[1:] for q in stored] == [("Why do you want to join us?\nWhat do you know about the team?",
                                        "I like the product.\nI read the engineering blog.",
                                        "Mention specific projects\nand link them to my experience.")]

    refresh(app)
    open_round(app, "Questions Co - Python Developer", "Round 1 — Recruiter / HR Screening")
    expect(app.get_by_text("Why do you want to join us?")).to_be_visible()
    expect(app.get_by_text("I like the product.")).to_be_visible()
    expect(app.get_by_text("Mention specific projects")).to_be_visible()
    expect_no_app_errors(app)


def test_optional_answers_left_blank_show_not_recorded(app, two_rounds):
    refresh(app)
    open_round(app, "Questions Co - Python Developer", "Round 2 — Technical Interview")
    save_question_via_ui(app, "Explain list comprehensions.", "A compact loop.", "Add an example.")
    save_question_via_ui(app, "What is a generator?")

    expect(app.get_by_text("Question 2", exact=True)).to_be_visible()
    expect(app.get_by_text("Not recorded", exact=True)).to_have_count(2)
    stored = db.get_questions_by_interview_id(two_rounds["round2"])
    assert [q[1:] for q in stored] == [("Explain list comprehensions.", "A compact loop.", "Add an example."),
                                       ("What is a generator?", None, None)]


def test_special_characters_and_long_text_are_shown_literally(app, two_rounds):
    question = "What does **kwargs do? <b>not bold</b> & 'quotes' — ✓"
    long_answer = "Long answer. " * 200
    refresh(app)
    open_round(app, "Questions Co - Python Developer", "Round 1 — Recruiter / HR Screening")
    save_question_via_ui(app, question, long_answer.strip(), "# not a heading")

    expect(app.get_by_text(question, exact=True)).to_be_visible()
    expect(app.get_by_text("# not a heading", exact=True)).to_be_visible()
    expect(app.get_by_role("heading", name="not a heading")).to_have_count(0)
    assert app.get_by_text("Long answer. Long answer.").inner_text() == long_answer.strip()
    assert db.get_questions_by_interview_id(two_rounds["round1"])[0][1] == question


def test_isolation_between_applications_and_rounds(app, two_rounds):
    db.create_interview_question(two_rounds["round1"], "Application A round 1 question")
    db.create_interview_question(two_rounds["round2"], "Application A round 2 question")
    other_app = db.create_application("Isolation B", "Data Engineer")
    other_round = db.create_interview(other_app, 1, 3)
    refresh(app)

    open_round(app, "Questions Co - Python Developer", "Round 1 — Recruiter / HR Screening")
    expect(app.get_by_text("Application A round 1 question")).to_be_visible()
    expect(app.get_by_text("Application A round 2 question")).to_have_count(0)

    choose(app, "Select Interview Round", "Round 2 — Technical Interview")
    expect(app.get_by_text("Application A round 2 question")).to_be_visible()
    expect(app.get_by_text("Application A round 1 question")).to_have_count(0)

    choose(app, "Select Application", "Isolation B - Data Engineer")
    expect(dropdown(app, "Select Interview Round")).to_have_value("Round 1 — Hiring Manager Interview")
    assert dropdown_options(app, "Select Interview Round") == ["Round 1 — Hiring Manager Interview"]
    expect(app.get_by_text("No questions recorded for this interview yet.")).to_be_visible()
    expect(app.get_by_text("Application A round")).to_have_count(0)
    save_question_via_ui(app, "Application B question")

    choose(app, "Select Application", "Questions Co - Python Developer")
    assert dropdown_options(app, "Select Interview Round") == ["Round 1 — Recruiter / HR Screening",
                                                               "Round 2 — Technical Interview"]
    expect(app.get_by_text("Application A round 1 question")).to_be_visible()
    expect(app.get_by_text("Application B question")).to_have_count(0)

    assert [q[1] for q in db.get_questions_by_interview_id(other_round)] == ["Application B question"]
    expect_no_app_errors(app)
