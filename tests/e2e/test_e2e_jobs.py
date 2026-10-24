"""UI Tests 2 & 3 — create and edit job applications in a real browser."""
import pytest
from playwright.sync_api import expect

import db
from ui_helpers import button, choose, dropdown, expect_no_app_errors, refresh, wait_for_table

pytestmark = pytest.mark.e2e


def create_application_via_ui(page, company, role, job_description="", url="", location="", notes=""):
    page.get_by_label("Company", exact=True).fill(company)
    page.get_by_label("Role", exact=True).fill(role)
    page.get_by_label("Job Description", exact=True).fill(job_description)
    page.get_by_label("Job URL", exact=True).fill(url)
    page.get_by_label("Location", exact=True).fill(location)
    page.get_by_label("Notes", exact=True).fill(notes)
    button(page, "Save Application").click()


def test_create_job_application(owner_id, app):
    create_application_via_ui(app, "E2E Corp", "QA Engineer", "Line 1 of JD\nLine 2 of JD",
                              "https://example.com/qa", "Remote", "Found on LinkedIn")

    expect(app.get_by_text("Application saved successfully! ID:")).to_be_visible()
    rows = wait_for_table(app, lambda rows: len(rows) == 1)
    assert (rows[0]["Company"], rows[0]["Role"], rows[0]["Status"]) == ("E2E Corp", "QA Engineer", "0")

    records = db.get_all_applications(owner_id)
    assert len(records) == 1 and rows[0]["id"] == records[0][0]
    assert db.get_application_by_id(owner_id, records[0][0])[1:7] == (
        "E2E Corp", "QA Engineer", "Line 1 of JD\nLine 2 of JD", "https://example.com/qa", "Remote",
        "Found on LinkedIn")

    refresh(app)
    rows = wait_for_table(app, lambda rows: len(rows) == 1)
    assert rows[0]["Company"] == "E2E Corp"
    expect(dropdown(app, "Select Application")).to_have_value("E2E Corp - QA Engineer")
    expect_no_app_errors(app)


def test_edit_job_application_preview_save_status_and_priority(owner_id, app):
    other_id = db.create_application(owner_id, "Other Co", "Other Role")
    app_id = db.create_application(owner_id, "Edit Me Co", "Junior Dev", "Old JD", "https://old.example.com", "Paris", "Old")
    other_before = db.get_application_by_id(owner_id, other_id)
    refresh(app)
    choose(app, "Select Application", "Edit Me Co - Junior Dev")
    expect(app.get_by_label("Edit Company", exact=True)).to_have_value("Edit Me Co")

    app.get_by_label("Edit Company", exact=True).fill("Edited Co")
    app.get_by_label("Edit Role", exact=True).fill("Senior Dev")
    app.get_by_label("Edit Job Description", exact=True).fill("New JD\nSecond line")
    app.get_by_label("Edit Job url", exact=True).fill("https://new.example.com")
    app.get_by_label("Edit Location", exact=True).fill("Berlin")
    app.get_by_label("Edit Job Notes", exact=True).fill("New notes")

    # Preview shows the values but must not write them.
    button(app, "Preview Changes").click()
    expect(app.get_by_text("Company : Edited Co")).to_be_visible()
    expect(app.get_by_text("Location : Berlin")).to_be_visible()
    assert db.get_application_by_id(owner_id, app_id)[1] == "Edit Me Co"

    button(app, "Save Edit Changes").click()
    expect(app.get_by_text(f"Application {app_id} is updated successfully!")).to_be_visible()
    saved = db.get_application_by_id(owner_id, app_id)
    assert saved[1:7] == ("Edited Co", "Senior Dev", "New JD\nSecond line", "https://new.example.com",
                          "Berlin", "New notes")

    choose(app, "Select Status", "Interviewing")
    choose(app, "Select Priority", "High")
    button(app, "Save Changes").click()
    expect(app.get_by_text(f"Application Changes Saved successfully! ID: {app_id}")).to_be_visible()

    refresh(app)
    choose(app, "Select Application", "Edited Co - Senior Dev")
    expect(app.get_by_label("Edit Company", exact=True)).to_have_value("Edited Co")
    expect(app.get_by_label("Edit Role", exact=True)).to_have_value("Senior Dev")
    expect(app.get_by_label("Edit Job Description", exact=True)).to_have_value("New JD\nSecond line")
    expect(app.get_by_label("Edit Location", exact=True)).to_have_value("Berlin")
    expect(dropdown(app, "Select Status")).to_have_value("Interviewing")
    expect(dropdown(app, "Select Priority")).to_have_value("High")
    record = db.get_application_by_id(owner_id, app_id)
    assert (record[9], record[11]) == (1, 3)
    assert record[0] == app_id and record[7] == saved[7]  # UUID and created_at preserved
    assert db.get_application_by_id(owner_id, other_id) == other_before
    expect_no_app_errors(app)
