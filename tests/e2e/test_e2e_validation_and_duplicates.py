"""UI Tests 8 & 9 — validation through rendered controls, and duplicate labels resolving to the right UUIDs."""
import pytest
from playwright.sync_api import expect

import db
from ui_helpers import (button, choose, dropdown_options, open_section, refresh, wait_for_table)

pytestmark = pytest.mark.e2e


def test_jobs_require_company_and_role(app, fetch_rows):
    app.get_by_label("Role", exact=True).fill("Developer")
    button(app, "Save Application").click()
    expect(app.get_by_text("Company and Role are required.")).to_be_visible()

    refresh(app)
    app.get_by_label("Company", exact=True).fill("Acme")
    app.get_by_label("Role", exact=True).fill("   ")
    button(app, "Save Application").click()
    expect(app.get_by_text("Company and Role are required.")).to_be_visible()
    assert fetch_rows("SELECT count(*) FROM applications") == [(0,)]


@pytest.mark.parametrize("invalid", ["0", "-3"])
def test_round_number_below_one_is_blocked(owner_id, app, invalid):
    app_id = db.create_application(owner_id, "Acme", "Dev")
    refresh(app)
    open_section(app, "Interviews")

    app.get_by_label("Round Number", exact=True).fill(invalid)
    button(app, "Save Interview").click()
    expect(app.get_by_text("below the allowed range")).to_be_visible()

    # A valid save afterwards proves the blocked attempt did not store anything.
    app.get_by_label("Round Number", exact=True).fill("1")
    button(app, "Save Interview").click()
    expect(app.get_by_text("Round 1 (Miscellaneous) saved for Acme - Dev.")).to_be_visible()
    assert [(r[1], r[2]) for r in db.get_interviews_by_application_id(owner_id, app_id)] == [(1, 0)]


@pytest.mark.parametrize("blank_question", ["", "   \n   "])
def test_empty_or_whitespace_question_rejected(owner_id, app, fetch_rows, blank_question):
    app_id = db.create_application(owner_id, "Acme", "Dev")
    db.create_interview(owner_id, app_id, 1, 1)
    refresh(app)
    open_section(app, "Questions")

    app.get_by_label("Interview Question", exact=True).fill(blank_question)
    app.get_by_label("My Answer / Apparent Answer (optional)", exact=True).fill("An answer with no question")
    button(app, "Save Question").click()

    expect(app.get_by_text("Interview question is required.")).to_be_visible()
    expect(app.get_by_text("No questions recorded for this interview yet.")).to_be_visible()
    assert fetch_rows("SELECT count(*) FROM interview_questions") == [(0,)]


def test_duplicate_labels_resolve_to_correct_uuids(owner_id, app):
    # Two applications with identical company and role, created through the UI.
    for expected_count in (1, 2):
        app.get_by_label("Company", exact=True).fill("Twin Co")
        app.get_by_label("Role", exact=True).fill("Twin Role")
        button(app, "Save Application").click()
        wait_for_table(app, lambda rows, n=expected_count: len(rows) == n)
    app_ids = [r[0] for r in db.get_all_applications(owner_id)]
    assert len(app_ids) == 2

    open_section(app, "Interviews")
    labels = dropdown_options(app, "Select Application")
    assert sorted(labels) == sorted(f"Twin Co - Twin Role ({app_id[:8]})" for app_id in app_ids)

    target_app = app_ids[1]
    target_label = f"Twin Co - Twin Role ({target_app[:8]})"
    choose(app, "Select Application", target_label)
    # Two identical rounds (same number and type) for the chosen application.
    for expected_count in (1, 2):
        app.get_by_label("Round Number", exact=True).fill("2")
        choose(app, "Round Type", "Technical Interview")
        button(app, "Save Interview").click()
        wait_for_table(app, lambda rows, n=expected_count: len(rows) == n)

    rounds = db.get_interviews_by_application_id(owner_id, target_app)
    assert len(rounds) == 2
    assert db.get_interviews_by_application_id(owner_id, app_ids[0]) == []

    open_section(app, "Questions")
    choose(app, "Select Application", target_label)
    round_labels = dropdown_options(app, "Select Interview Round")
    assert sorted(round_labels) == sorted(f"Round 2 — Technical Interview ({r[0][:8]})" for r in rounds)

    target_round = rounds[1][0]
    choose(app, "Select Interview Round", f"Round 2 — Technical Interview ({target_round[:8]})")
    app.get_by_label("Interview Question", exact=True).fill("Asked in the second duplicate round")
    button(app, "Save Question").click()
    expect(app.get_by_text("Asked in the second duplicate round")).to_be_visible()

    assert [q[1] for q in db.get_questions_by_interview_id(owner_id, target_round)] == ["Asked in the second duplicate round"]
    assert db.get_questions_by_interview_id(owner_id, rounds[0][0]) == []
