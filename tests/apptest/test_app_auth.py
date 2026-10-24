"""AppTest: Google login gate, open registration, rejected identities, signed-in name and Logout."""
import pytest

import db
from app_helpers import click, new_app, open_app, texts
from auth_helpers import OTHER_USER, TEST_USER, TEST_USER_SUB


@pytest.fixture
def init_db_calls(monkeypatch):
    """Record calls to db.init_db so tests can prove the database is not touched before authentication."""
    calls = []
    real_init_db = db.init_db
    monkeypatch.setattr(db, "init_db", lambda *args, **kwargs: (calls.append(1), real_init_db(*args, **kwargs))[1])
    return calls


def visible_text(at):
    return [*texts(at.title), *texts(at.markdown), *texts(at.caption), *texts(at.error), *texts(at.info)]


def assert_crm_hidden(at, seeded_names=()):
    assert not at.exception
    assert len(at.sidebar.radio) == 0
    assert "Logout" not in [b.label for b in at.button]
    assert not at.header
    for name in seeded_names:
        assert all(name not in text for text in visible_text(at))


def test_unauthenticated_visitor_sees_only_login_screen(sign_in_as, seeded, init_db_calls):
    sign_in_as(None)
    at = new_app().run()
    assert_crm_hidden(at, ["Acme Corp", "Globex"])
    assert [b.label for b in at.button] == ["Sign in with Google"]
    assert init_db_calls == []


def test_sign_in_button_starts_google_login(sign_in_as, monkeypatch):
    sign_in_as(None)
    login_calls = []
    monkeypatch.setattr("streamlit.login", lambda *args, **kwargs: login_calls.append(args))
    at = new_app().run()
    click(at, "Sign in with Google")
    assert login_calls == [()]


def test_first_sign_in_registers_the_google_account(fetch_rows):
    assert fetch_rows("SELECT count(*) FROM users") == [(0,)]
    at = open_app()
    assert "No saved applications yet." in texts(at.info)
    users = fetch_rows("SELECT id, google_sub, email, name, created_at FROM users")
    assert len(users) == 1
    user_id, sub, email, name, created_at = users[0]
    assert (sub, email, name) == (TEST_USER_SUB, TEST_USER["email"], TEST_USER["name"])
    assert user_id != sub and created_at  # internal id, not the Google identifier


def test_returning_user_gets_the_same_account_and_data(seeded, owner_id, fetch_rows):
    for _ in range(3):  # separate sessions and reruns
        at = open_app()
        at.sidebar.radio[0].set_value("Questions").run()
    assert fetch_rows("SELECT id FROM users") == [(owner_id,)]
    at = open_app()
    assert set(at.dataframe[0].value["Company"]) == {"Acme Corp", "Globex"}


def test_returning_user_profile_is_refreshed_but_identity_is_the_sub(sign_in_as, owner_id, fetch_rows):
    sign_in_as({**TEST_USER, "email": "new-address@example.com", "name": "Renamed Owner"})
    open_app()
    assert fetch_rows("SELECT id, email, name FROM users") == [(owner_id, "new-address@example.com", "Renamed Owner")]


def test_a_different_google_account_gets_its_own_empty_workspace(sign_in_as, seeded, fetch_rows):
    sign_in_as(OTHER_USER)
    at = open_app()
    assert "**Someone Else**" in texts(at.markdown)
    assert "No saved applications yet." in texts(at.info)
    assert [t for t in visible_text(at) if "Acme Corp" in t or "Globex" in t] == []
    assert {row[0] for row in fetch_rows("SELECT google_sub FROM users")} == {TEST_USER_SUB, OTHER_USER["sub"]}


def test_same_email_with_a_different_sub_is_a_different_account(sign_in_as, seeded, fetch_rows):
    # Email is display data only: an account that reuses the owner's email is still a separate user.
    sign_in_as({"sub": "attacker-sub", "email": TEST_USER["email"], "name": TEST_USER["name"]})
    at = open_app()
    assert "No saved applications yet." in texts(at.info)
    assert fetch_rows("SELECT count(*) FROM users") == [(2,)]


@pytest.mark.parametrize("claims", [
    {}, {"name": "No Sub"}, {"sub": ""}, {"sub": None}, {"sub": "   "}, {"sub": " padded-sub "},
    {"sub": 12345}, {"sub": ["a", "b"]}, {"sub": "x" * 256}, {"sub": "line\nbreak"},
], ids=["no-claims", "name-only", "empty", "none", "blank", "padded", "int", "list", "too-long", "newline"])
def test_missing_or_invalid_sub_is_denied(sign_in_as, seeded, claims, init_db_calls, fetch_rows):
    sign_in_as(claims)
    at = new_app().run()
    assert_crm_hidden(at, ["Acme Corp", "Globex"])
    assert texts(at.error) == ["Access Denied"]
    assert init_db_calls == []
    assert fetch_rows("SELECT count(*) FROM users") == [(1,)]  # only the seeded owner


def test_signed_in_user_sees_name_logout_and_crm(init_db_calls):
    at = open_app()
    assert "**Test Owner**" in texts(at.markdown)
    assert "Logout" in [b.label for b in at.button]
    assert at.sidebar.radio[0].options == ["Jobs", "Interviews", "Questions", "Insights"]
    assert texts(at.header)[0] == "Jobs"
    assert init_db_calls == [1]


@pytest.mark.parametrize("claims, expected", [
    ({"name": "Full Name", "given_name": "Given", "family_name": "Family"}, "Full Name"),
    ({"given_name": "Given", "family_name": "Family", "email": "a@example.com"}, "Given Family"),
    ({"given_name": "Given"}, "Given"),
    ({"email": "a@example.com"}, "a@example.com"),
    ({}, "Signed-in user"),
])
def test_display_name_fallbacks(sign_in_as, claims, expected):
    sign_in_as({"sub": TEST_USER_SUB, **claims})
    at = open_app()
    assert f"**{expected}**" in texts(at.markdown)


def test_oidc_claims_and_internal_ids_are_not_displayed(seeded, owner_id):
    at = open_app()
    shown = " ".join(visible_text(at) + [str(j.value) for j in at.json] + texts(at.success))
    assert TEST_USER_SUB not in shown
    assert TEST_USER["email"] not in shown
    assert owner_id not in shown
    assert "user_id" not in list(at.dataframe[0].value.columns)


def test_logout_returns_to_login_screen(seeded):
    at = open_app()
    click(at, "Logout")
    assert_crm_hidden(at, ["Acme Corp", "Globex"])
    assert [b.label for b in at.button] == ["Sign in with Google"]


def test_identity_is_re_resolved_on_every_run(app_user, seeded):
    """Switching the signed-in account mid-session immediately switches the visible data."""
    at = open_app()
    assert set(at.dataframe[0].value["Company"]) == {"Acme Corp", "Globex"}
    app_user.clear()
    app_user.update({"is_logged_in": True, **OTHER_USER})
    at.run()
    assert "No saved applications yet." in texts(at.info)
    assert len(at.dataframe) == 0


def test_after_logout_another_account_cannot_see_previous_users_data(app_user, seeded):
    at = open_app()
    click(at, "Logout")
    app_user.update({"is_logged_in": True, **OTHER_USER})
    at.run()
    assert "**Someone Else**" in texts(at.markdown)
    assert "No saved applications yet." in texts(at.info)


def test_session_state_cannot_override_the_user(seeded, other_user_id):
    """Values a client could influence through session state are never used as the user id."""
    at = new_app()
    at.session_state["user_id"] = other_user_id
    at.session_state["current_user_id"] = other_user_id
    at.run()
    assert set(at.dataframe[0].value["Company"]) == {"Acme Corp", "Globex"}


PRIVACY_URL = "https://sagarjain.in/interview-crm/privacy/"
TERMS_URL = "https://sagarjain.in/interview-crm/terms/"
LEGAL_LINKS = f"[Privacy Policy]({PRIVACY_URL}) · [Terms of Service]({TERMS_URL})"


def test_login_screen_links_privacy_policy_and_terms(sign_in_as):
    sign_in_as(None)
    at = new_app().run()
    assert LEGAL_LINKS in texts(at.caption)


def test_sidebar_links_privacy_policy_and_terms():
    at = open_app()
    assert LEGAL_LINKS in texts(at.sidebar.caption)
