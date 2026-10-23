"""AppTest: Interviews page (Step 6)."""
import db
from app_helpers import by_label, click, contains, open_app, texts

ROUND_TYPE_LABELS = ["Miscellaneous", "Recruiter / HR Screening", "Technical Interview",
                     "Hiring Manager Interview", "Behavioral / Culture Fit"]


def add_round(at, number, round_type):
    by_label(at.number_input, "Round Number").set_value(number)
    by_label(at.selectbox, "Round Type").set_value(round_type)
    return click(at, "Save Interview")


def test_no_applications_state():
    at = open_app("Interviews")
    assert "No saved applications yet. Add one on the Jobs page first." in texts(at.info)
    assert len(at.number_input) == 0


def test_form_controls_exist_with_readable_round_types(seeded):
    at = open_app("Interviews")
    number = by_label(at.number_input, "Round Number")
    assert (number.value, number.min) == (1, 1)
    assert by_label(at.selectbox, "Round Type").options == ROUND_TYPE_LABELS
    by_label(at.button, "Save Interview")


def test_empty_interview_state_for_application_without_rounds():
    db.create_application("Acme", "Dev")
    at = open_app("Interviews")
    assert "No interviews recorded for this application yet." in texts(at.info)


def test_saving_round_appears_immediately_with_readable_labels(fetch_rows):
    app_id = db.create_application("Acme", "Dev")
    at = open_app("Interviews")
    add_round(at, 2, 2)

    assert "Round 2 (Technical Interview) saved for Acme - Dev." in texts(at.success)
    assert fetch_rows("SELECT application_id, round_number, round_type, result FROM interviews") == [(app_id, 2, 2, 0)]
    table = at.dataframe[0].value
    assert list(table.columns) == ["Interview ID", "Round Number", "Round Type", "Result"]
    assert list(table["Round Type"]) == ["Technical Interview"]
    assert list(table["Result"]) == ["Scheduled"]


def test_rounds_sorted_by_round_number():
    db.create_application("Acme", "Dev")
    at = open_app("Interviews")
    for number, round_type in [(3, 3), (1, 1), (2, 4)]:
        add_round(at, number, round_type)
    table = at.dataframe[0].value
    assert list(table["Round Number"]) == [1, 2, 3]
    assert list(table["Round Type"]) == ["Recruiter / HR Screening", "Behavioral / Culture Fit",
                                         "Hiring Manager Interview"]


def test_round_saved_for_the_selected_application(seeded, fetch_rows):
    at = open_app("Interviews")
    by_label(at.selectbox, "Select Application").set_value(seeded["app_b"]).run()
    add_round(at, 2, 0)
    assert fetch_rows("SELECT application_id FROM interviews WHERE round_number=2 AND round_type=0") == [
        (seeded["app_b"],)]


def test_switching_applications_shows_correct_rounds(seeded):
    at = open_app("Interviews")
    by_label(at.selectbox, "Select Application").set_value(seeded["app_a"]).run()
    assert set(at.dataframe[0].value["Interview ID"]) == {seeded["a_round1"], seeded["a_round2"]}
    by_label(at.selectbox, "Select Application").set_value(seeded["app_b"]).run()
    assert list(at.dataframe[0].value["Interview ID"]) == [seeded["b_round1"]]


def test_round_number_zero_is_never_stored(fetch_rows):
    """The browser blocks 0 (see e2e tests). Server-side, Streamlit replaces the out-of-range
    value with the widget default, so we can only assert that 0 never reaches SQLite."""
    db.create_application("Acme", "Dev")
    at = open_app("Interviews")
    add_round(at, 0, 1)
    assert fetch_rows("SELECT count(*) FROM interviews WHERE round_number < 1") == [(0,)]


def test_adding_round_does_not_change_application_status(seeded):
    before = db.get_application_by_id(seeded["app_a"])
    at = open_app("Interviews")
    by_label(at.selectbox, "Select Application").set_value(seeded["app_a"]).run()
    add_round(at, 3, 2)
    assert contains(at.success, "Round 3")
    assert db.get_application_by_id(seeded["app_a"]) == before
