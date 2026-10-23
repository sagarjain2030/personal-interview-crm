"""UI Test 10 — persistence across navigation, refresh, new browser sessions and reruns."""
import pytest
from playwright.sync_api import expect

import db
from ui_helpers import button, choose, open_section, refresh, wait_for_table

pytestmark = pytest.mark.e2e

APP_LABEL = "Persist Co - SRE"


def test_full_workflow_survives_navigation_refresh_and_new_session(app, open_new_session):
    # Create everything through the UI.
    app.get_by_label("Company", exact=True).fill("Persist Co")
    app.get_by_label("Role", exact=True).fill("SRE")
    button(app, "Save Application").click()
    expect(app.get_by_text("Application saved successfully!")).to_be_visible()

    open_section(app, "Interviews")
    app.get_by_label("Round Number", exact=True).fill("1")
    choose(app, "Round Type", "Behavioral / Culture Fit")
    button(app, "Save Interview").click()
    expect(app.get_by_text(f"Round 1 (Behavioral / Culture Fit) saved for {APP_LABEL}.")).to_be_visible()

    open_section(app, "Questions")
    app.get_by_label("Interview Question", exact=True).fill("Tell me about a conflict.")
    app.get_by_label("My Answer / Apparent Answer (optional)", exact=True).fill("STAR story about a release.")
    button(app, "Save Question").click()
    expect(app.get_by_text("Tell me about a conflict.")).to_be_visible()

    # Navigate away and back.
    open_section(app, "Insights")
    open_section(app, "Questions")
    expect(app.get_by_text("Tell me about a conflict.")).to_be_visible()

    # Browser refresh.
    refresh(app)
    open_section(app, "Interviews")
    rows = wait_for_table(app, lambda rows: len(rows) == 1)
    assert rows[0]["Round Type"] == "Behavioral / Culture Fit"

    # Completely new browser context (new Streamlit session).
    other = open_new_session()
    rows = wait_for_table(other, lambda rows: len(rows) == 1)
    assert rows[0]["Company"] == "Persist Co"
    open_section(other, "Questions")
    expect(other.get_by_text("Tell me about a conflict.")).to_be_visible()
    expect(other.get_by_text("STAR story about a release.")).to_be_visible()

    app_id = db.get_all_applications()[0][0]
    interview_id = db.get_interviews_by_application_id(app_id)[0][0]
    assert [q[1:3] for q in db.get_questions_by_interview_id(interview_id)] == [
        ("Tell me about a conflict.", "STAR story about a release.")]


def test_form_saves_into_the_currently_selected_round_and_reruns_lose_nothing(app):
    app_id = db.create_application("Persist Co", "SRE")
    round1 = db.create_interview(app_id, 1, 1)
    round2 = db.create_interview(app_id, 2, 2)
    db.create_interview_question(round1, "Existing round 1 question")
    refresh(app)
    open_section(app, "Questions")
    expect(app.get_by_text("Existing round 1 question")).to_be_visible()

    # Switch to round 2 before typing: the question must go to round 2 only.
    choose(app, "Select Interview Round", "Round 2 — Technical Interview")
    app.get_by_label("Interview Question", exact=True).fill("New round 2 question")
    button(app, "Save Question").click()
    expect(app.get_by_text("New round 2 question")).to_be_visible()
    expect(app.get_by_text("Existing round 1 question")).to_have_count(0)

    # Several reruns (selection changes, navigation) must not lose or duplicate anything.
    for round_label in ["Round 1 — Recruiter / HR Screening", "Round 2 — Technical Interview",
                        "Round 1 — Recruiter / HR Screening"]:
        choose(app, "Select Interview Round", round_label)
    expect(app.get_by_text("Existing round 1 question")).to_be_visible()
    expect(app.get_by_text("New round 2 question")).to_have_count(0)
    open_section(app, "Jobs")
    open_section(app, "Questions")

    assert [q[1] for q in db.get_questions_by_interview_id(round1)] == ["Existing round 1 question"]
    assert [q[1] for q in db.get_questions_by_interview_id(round2)] == ["New round 2 question"]
