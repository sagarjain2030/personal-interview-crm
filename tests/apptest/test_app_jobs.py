"""AppTest: Jobs page (Steps 3–5)."""
import pytest

import db
from app_helpers import by_label, click, contains, open_app, texts

FORM_TEXT_INPUTS = ["Company", "Role", "Job URL", "Location"]
FORM_TEXT_AREAS = ["Job Description", "Notes"]


def fill_new_application(at, company, role, **optional):
    by_label(at.text_input, "Company").input(company)
    by_label(at.text_input, "Role").input(role)
    for label, value in optional.items():
        widgets = at.text_area if label in FORM_TEXT_AREAS else at.text_input
        by_label(widgets, label).input(value)


def test_application_form_fields_exist():
    at = open_app()
    for label in FORM_TEXT_INPUTS:
        by_label(at.text_input, label)
    for label in FORM_TEXT_AREAS:
        by_label(at.text_area, label)
    by_label(at.button, "Save Application")


def test_empty_database_state():
    at = open_app()
    assert "No saved applications yet." in texts(at.info)
    assert len(at.dataframe) == 0


@pytest.mark.parametrize("company, role", [("", "Dev"), ("Acme", ""), ("   ", "Dev"), ("Acme", "  ")])
def test_company_and_role_are_required(company, role, fetch_rows):
    at = open_app()
    fill_new_application(at, company, role)
    click(at, "Save Application")
    assert "Company and Role are required." in texts(at.error)
    assert fetch_rows("SELECT count(*) FROM applications") == [(0,)]


def test_valid_application_is_saved_and_listed(fetch_rows):
    at = open_app()
    fill_new_application(at, "  Acme Corp  ", "Python Developer", **{
        "Job Description": "Build things.\nTest things.", "Job URL": "https://example.com",
        "Location": "Remote", "Notes": "Referral"})
    click(at, "Save Application")

    assert contains(at.success, "Application saved successfully! ID:")
    rows = fetch_rows("SELECT company, role, raw_job_description, jd_url, location, notes FROM applications")
    assert rows == [("Acme Corp", "Python Developer", "Build things.\nTest things.",
                     "https://example.com", "Remote", "Referral")]
    listing = at.dataframe[0].value
    assert list(listing["Company"]) == ["Acme Corp"]


def test_selection_is_uuid_backed_with_readable_labels(seeded):
    at = open_app()
    selector = by_label(at.selectbox, "Select Application")
    assert set(selector.options) == {"Acme Corp - Python Developer", "Globex - Data Engineer"}
    selector.set_value(seeded["app_a"]).run()
    assert by_label(at.selectbox, "Select Application").value == seeded["app_a"]
    assert by_label(at.text_input, "Edit Company").value == "Acme Corp"


def test_duplicate_company_role_labels_are_distinguishable():
    first = db.create_application("Same Co", "Same Role")
    second = db.create_application("Same Co", "Same Role")
    at = open_app()
    options = by_label(at.selectbox, "Select Application").options
    assert sorted(options) == sorted([f"Same Co - Same Role ({first[:8]})", f"Same Co - Same Role ({second[:8]})"])

    by_label(at.selectbox, "Select Application").set_value(second).run()
    assert by_label(at.selectbox, "Select Application").value == second


def test_preview_does_not_write_to_database(seeded):
    before = db.get_application_by_id(seeded["app_a"])
    at = open_app()
    by_label(at.selectbox, "Select Application").set_value(seeded["app_a"]).run()
    by_label(at.text_input, "Edit Company").input("Preview Co")
    click(at, "Preview Changes")

    assert "Company : Preview Co" in texts(at.markdown)
    assert db.get_application_by_id(seeded["app_a"]) == before


def test_preview_with_empty_company_shows_error(seeded):
    at = open_app()
    by_label(at.text_input, "Edit Company").input("   ")
    click(at, "Preview Changes")
    assert "Company and Role details are required." in texts(at.error)


def test_save_edits_updates_only_selected_application(seeded):
    other_before = db.get_application_by_id(seeded["app_b"])
    at = open_app()
    by_label(at.selectbox, "Select Application").set_value(seeded["app_a"]).run()
    by_label(at.text_input, "Edit Company").input("  Acme Updated ")
    by_label(at.text_input, "Edit Role").input("Senior Python Developer")
    by_label(at.text_area, "Edit Job Description").input("New JD")
    by_label(at.text_input, "Edit Job url").input("https://new.example.com")
    by_label(at.text_input, "Edit Location").input("Berlin")
    by_label(at.text_area, "Edit Job Notes").input("Updated notes")
    click(at, "Save Edit Changes")

    assert contains(at.success, "is updated successfully")
    updated = db.get_application_by_id(seeded["app_a"])
    assert updated[1:7] == ("Acme Updated", "Senior Python Developer", "New JD",
                            "https://new.example.com", "Berlin", "Updated notes")
    assert db.get_application_by_id(seeded["app_b"]) == other_before


def test_save_edits_with_empty_role_is_rejected(seeded):
    before = db.get_application_by_id(seeded["app_a"])
    at = open_app()
    by_label(at.selectbox, "Select Application").set_value(seeded["app_a"]).run()
    by_label(at.text_input, "Edit Role").input("")
    click(at, "Save Edit Changes")
    assert "Company and Role details are required." in texts(at.error)
    assert db.get_application_by_id(seeded["app_a"]) == before


def test_status_and_priority_dropdowns_show_and_save_values(seeded):
    db.update_application_status(seeded["app_a"], 1)
    at = open_app()
    by_label(at.selectbox, "Select Application").set_value(seeded["app_a"]).run()
    status = by_label(at.selectbox, "Select Status")
    priority = by_label(at.selectbox, "Select Priority")
    assert (status.value, priority.value) == (1, 2)
    assert status.options == ["Applied", "Interviewing", "Application Rejected", "Application Withdrawn",
                              "Offer Received", "Offer Accepted", "Offer Declined"]
    assert priority.options == ["Low", "Medium", "High"]

    status.set_value(4)
    priority.set_value(3)
    click(at, "Save Changes")

    assert contains(at.success, "Application Changes Saved successfully!")
    record = db.get_application_by_id(seeded["app_a"])
    assert (record[9], record[11]) == (4, 3)
    other = db.get_application_by_id(seeded["app_b"])
    assert (other[9], other[11]) == (0, 2)

    fresh = open_app()
    by_label(fresh.selectbox, "Select Application").set_value(seeded["app_a"]).run()
    assert by_label(fresh.selectbox, "Select Status").value == 4
    assert by_label(fresh.selectbox, "Select Priority").value == 3
