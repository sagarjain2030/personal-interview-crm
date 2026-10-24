"""AppTest: Google login gate, single-user authorization, signed-in name and Logout."""
import pytest

import db
from app_helpers import click, new_app, open_app, texts
from auth_helpers import AUTHORIZED_USER, TEST_ALLOWED_SUB, UNAUTHORIZED_USER


@pytest.fixture
def init_db_calls(monkeypatch):
    """Record calls to db.init_db so tests can prove the database is not touched before authorization."""
    calls = []
    real_init_db = db.init_db
    monkeypatch.setattr(db, "init_db", lambda: (calls.append(1), real_init_db())[1])
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


def test_unauthorized_account_is_denied(sign_in_as, seeded, init_db_calls):
    sign_in_as(UNAUTHORIZED_USER)
    at = new_app().run()
    assert_crm_hidden(at, ["Acme Corp", "Globex"])
    assert texts(at.error) == ["Access Denied"]
    assert "Someone Else" not in visible_text(at)
    assert init_db_calls == []


@pytest.mark.parametrize("claims", [{}, {"name": "No Sub"}, {"sub": ""}])
def test_logged_in_without_matching_sub_is_denied(sign_in_as, claims):
    sign_in_as(claims)
    at = new_app().run()
    assert_crm_hidden(at)
    assert texts(at.error) == ["Access Denied"]


def test_empty_allowed_sub_secret_denies_everyone(sign_in_as):
    sign_in_as({"sub": ""})
    at = new_app()
    at.secrets["access"] = {"allowed_google_sub": ""}
    at.run()
    assert_crm_hidden(at)
    assert texts(at.error) == ["Access Denied"]


def test_authorized_owner_sees_name_logout_and_crm(init_db_calls):
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
    sign_in_as({"sub": TEST_ALLOWED_SUB, **claims})
    at = open_app()
    assert f"**{expected}**" in texts(at.markdown)


def test_oidc_claims_are_not_displayed():
    at = open_app()
    shown = " ".join(visible_text(at) + [str(j.value) for j in at.json])
    assert TEST_ALLOWED_SUB not in shown
    assert AUTHORIZED_USER["email"] not in shown


def test_logout_returns_to_login_screen(seeded):
    at = open_app()
    click(at, "Logout")
    assert_crm_hidden(at, ["Acme Corp", "Globex"])
    assert [b.label for b in at.button] == ["Sign in with Google"]
