"""UI Test 4 — create interview rounds in a real browser."""
import pytest
from playwright.sync_api import expect

import db
from ui_helpers import button, choose, expect_no_app_errors, open_section, refresh, wait_for_table

pytestmark = pytest.mark.e2e


def add_round_via_ui(page, number, round_type, application_label):
    page.get_by_label("Round Number", exact=True).fill(str(number))
    choose(page, "Round Type", round_type)
    button(page, "Save Interview").click()
    expect(page.get_by_text(f"Round {number} ({round_type}) saved for {application_label}.")).to_be_visible()


def test_create_interview_rounds(app):
    other_id = db.create_application("Other Co", "Other Role")
    app_id = db.create_application("Rounds Co", "Backend Dev")
    other_status_before = db.get_application_by_id(app_id)[9]
    refresh(app)
    open_section(app, "Interviews")
    choose(app, "Select Application", "Rounds Co - Backend Dev")
    expect(app.get_by_text("No interviews recorded for this application yet.")).to_be_visible()

    # Saved out of order on purpose: round 2 first, then round 1.
    add_round_via_ui(app, 2, "Technical Interview", "Rounds Co - Backend Dev")
    add_round_via_ui(app, 1, "Recruiter / HR Screening", "Rounds Co - Backend Dev")

    rows = wait_for_table(app, lambda rows: len(rows) == 2)
    assert [(r["Round Number"], r["Round Type"], r["Result"]) for r in rows] == [
        ("1", "Recruiter / HR Screening", "Scheduled"),
        ("2", "Technical Interview", "Scheduled"),
    ]
    stored = db.get_interviews_by_application_id(app_id)
    assert [r[0] for r in stored] == [r["Interview ID"] for r in rows]
    assert [(r[1], r[2], r[3]) for r in stored] == [(1, 1, 0), (2, 2, 0)]
    assert db.get_interviews_by_application_id(other_id) == []
    assert db.get_application_by_id(app_id)[9] == other_status_before  # status not changed

    refresh(app)
    open_section(app, "Interviews")
    choose(app, "Select Application", "Rounds Co - Backend Dev")
    rows = wait_for_table(app, lambda rows: len(rows) == 2)
    assert [r["Round Number"] for r in rows] == ["1", "2"]

    choose(app, "Select Application", "Other Co - Other Role")
    expect(app.get_by_text("No interviews recorded for this application yet.")).to_be_visible()
    expect_no_app_errors(app)
