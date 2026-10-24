"""AppTest: two Google accounts using the CRM side by side, and the legacy-data upgrade at start-up."""
import pytest

import db
from app_helpers import by_label, click, contains, new_app, open_app, texts
from auth_helpers import LEGACY_OWNER_SUB, OTHER_USER, TEST_USER
from legacy_db import LEGACY_IDS, create_legacy_db


@pytest.fixture
def other_data(other_user_id):
    app_id = db.create_application(other_user_id, "Other Inc", "Hidden Role", notes="other's notes")
    interview_id = db.create_interview(other_user_id, app_id, 1, 4)
    db.create_interview_question(other_user_id, interview_id, "Other user's private question")
    return {"app": app_id, "interview": interview_id}


def options(at, label):
    return by_label(at.selectbox, label).options


def test_jobs_page_lists_only_the_signed_in_users_applications(seeded, other_data):
    at = open_app()
    assert set(at.dataframe[0].value["Company"]) == {"Acme Corp", "Globex"}
    assert set(options(at, "Select Application")) == {"Acme Corp - Python Developer", "Globex - Data Engineer"}


def test_other_user_sees_only_their_own_records_on_every_page(sign_in_as, seeded, other_data):
    sign_in_as(OTHER_USER)
    at = open_app()
    assert list(at.dataframe[0].value["Company"]) == ["Other Inc"]
    assert options(at, "Select Application") == ["Other Inc - Hidden Role"]

    at.sidebar.radio[0].set_value("Interviews").run()
    assert options(at, "Select Application") == ["Other Inc - Hidden Role"]
    assert list(at.dataframe[0].value["Interview ID"]) == [other_data["interview"]]

    at.sidebar.radio[0].set_value("Questions").run()
    assert texts(at.text) == ["Other user's private question", "Not recorded", "Not recorded"]
    assert not contains(at.text, "decorator")


def test_records_saved_through_the_ui_belong_to_the_signed_in_user(sign_in_as, owner_id, other_user_id):
    sign_in_as(OTHER_USER)
    at = open_app()
    by_label(at.text_input, "Company").input("Other Saved Co")
    by_label(at.text_input, "Role").input("Role")
    click(at, "Save Application")
    assert [r[1] for r in db.get_all_applications(other_user_id)] == ["Other Saved Co"]
    assert db.get_all_applications(owner_id) == []

    sign_in_as(TEST_USER)
    at = open_app()
    assert "No saved applications yet." in texts(at.info)


def test_selecting_another_users_application_id_directly_is_denied(seeded, other_data):
    """Forcing a foreign UUID into the selectbox (as a tampered client might) shows nothing of it."""
    at = open_app()
    # A selectbox value is resolved against the options of this run (the user's own records), so a
    # foreign UUID cannot even be submitted; the data layer would deny it anyway (test_db_isolation.py).
    with pytest.raises(ValueError, match="not in list"):
        by_label(at.selectbox, "Select Application").set_value(other_data["app"]).run()
    assert db.get_application_by_id(db.get_or_create_user(TEST_USER["sub"]), other_data["app"]) is None


def test_editing_saves_never_touch_another_users_records(seeded, other_data, other_user_id):
    other_before = db.get_application_by_id(other_user_id, other_data["app"])
    at = open_app()
    by_label(at.text_input, "Edit Company").input("Changed")
    click(at, "Save Edit Changes")
    by_label(at.selectbox, "Select Status").set_value(5)
    click(at, "Save Changes")
    at.sidebar.radio[0].set_value("Interviews").run()
    click(at, "Save Interview")
    at.sidebar.radio[0].set_value("Questions").run()
    by_label(at.text_area, "Interview Question").input("Mine")
    click(at, "Save Question")
    assert db.get_application_by_id(other_user_id, other_data["app"]) == other_before
    assert len(db.get_interviews_by_application_id(other_user_id, other_data["app"])) == 1
    assert len(db.get_questions_by_interview_id(other_user_id, other_data["interview"])) == 1


# --- Legacy single-user database at start-up -------------------------------------------------

def legacy_app(owner_sub):
    at = new_app()
    at.secrets["access"] = {"allowed_google_sub": owner_sub}
    return at


def test_legacy_data_is_migrated_to_the_configured_owner(sign_in_as, test_db_path):
    create_legacy_db(test_db_path)
    sign_in_as({"sub": LEGACY_OWNER_SUB, "name": "Legacy Owner", "email": "legacy@example.com"})
    at = legacy_app(LEGACY_OWNER_SUB).run()
    assert not at.exception
    assert set(at.dataframe[0].value["Company"]) == {"Legacy Corp", "Old Globex"}
    assert set(at.dataframe[0].value["id"]) == {LEGACY_IDS["app_a"], LEGACY_IDS["app_b"]}


def test_after_migration_other_accounts_do_not_see_legacy_data(sign_in_as, test_db_path):
    create_legacy_db(test_db_path)
    sign_in_as(OTHER_USER)  # the first person to sign in is not the legacy owner
    at = legacy_app(LEGACY_OWNER_SUB).run()
    assert "No saved applications yet." in texts(at.info)
    assert not contains(at.markdown, "Legacy Corp")


def test_legacy_data_without_a_configured_owner_stops_the_app(test_db_path):
    create_legacy_db(test_db_path)
    file_before = test_db_path.read_bytes()
    at = new_app().run()  # default test secrets: no legacy owner
    assert not at.exception
    assert texts(at.error) == [
        "The CRM database needs a one-time upgrade by the administrator. Please try again later."]
    assert len(at.sidebar.radio) == 0
    assert "Logout" in [b.label for b in at.button]  # the user can still sign out
    assert test_db_path.read_bytes() == file_before
