"""AppTest: sidebar navigation renders every section without exceptions."""
import pytest

from app_helpers import open_app


@pytest.mark.parametrize("section", ["Jobs", "Interviews", "Questions", "Insights"])
def test_each_section_renders_its_header(section, seeded):
    at = open_app(section)
    assert at.title[0].value == "Personal Interview CRM"
    assert at.header[0].value == section
    assert not at.exception


def test_navigation_options():
    at = open_app()
    assert list(at.sidebar.radio[0].options) == ["Jobs", "Interviews", "Questions", "Insights"]


def test_insights_shows_placeholder():
    at = open_app("Insights")
    assert at.markdown[-1].value == "Interview insights will appear here in a later step."


def test_switching_between_all_sections_in_one_session(seeded):
    at = open_app()
    for section in ["Interviews", "Questions", "Insights", "Jobs", "Questions"]:
        at.sidebar.radio[0].set_value(section).run()
        assert not at.exception
        assert at.header[0].value == section
