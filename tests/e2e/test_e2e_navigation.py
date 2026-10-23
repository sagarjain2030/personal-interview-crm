"""UI Test 1 — navigation in a real Chromium browser."""
import pytest
from playwright.sync_api import expect

import db
from ui_helpers import expect_no_app_errors, open_section, refresh

pytestmark = pytest.mark.e2e


def test_title_and_sidebar_navigation(app):
    expect(app.get_by_role("heading", name="Personal Interview CRM", level=1)).to_be_visible()
    navigation = app.get_by_role("radiogroup", name="Navigation")
    for section in ["Jobs", "Interviews", "Questions", "Insights"]:
        expect(navigation.get_by_role("radio", name=section)).to_have_count(1)
    expect(navigation.get_by_role("radio", name="Jobs")).to_be_checked()


def test_each_section_renders_expected_content_on_empty_database(app):
    expect(app.get_by_role("button", name="Save Application")).to_be_visible()
    expect(app.get_by_text("No saved applications yet.")).to_be_visible()

    open_section(app, "Interviews")
    expect(app.get_by_text("No saved applications yet. Add one on the Jobs page first.")).to_be_visible()

    open_section(app, "Questions")
    expect(app.get_by_text("No saved applications yet. Add one on the Jobs page first.")).to_be_visible()

    open_section(app, "Insights")
    expect(app.get_by_text("Interview insights will appear here in a later step.")).to_be_visible()
    expect_no_app_errors(app)


def test_sections_render_with_data_and_no_errors(app):
    app_id = db.create_application("Acme Corp", "Python Developer")
    interview_id = db.create_interview(app_id, 1, 2)
    db.create_interview_question(interview_id, "Seeded question?")
    refresh(app)

    expect(app.get_by_role("heading", name="Saved Applications")).to_be_visible()
    open_section(app, "Interviews")
    expect(app.get_by_role("heading", name="Interview Rounds")).to_be_visible()
    open_section(app, "Questions")
    expect(app.get_by_text("Seeded question?")).to_be_visible()
    open_section(app, "Jobs")
    expect(app.get_by_label("Edit Company", exact=True)).to_have_value("Acme Corp")
    expect_no_app_errors(app)
