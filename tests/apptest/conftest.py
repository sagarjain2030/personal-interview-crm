"""AppTest fixtures: simulate the Google account Streamlit reports through st.user.

AppTest has no real OIDC login, so `st.user` is backed by a dict the test controls. By default every
AppTest runs as TEST_USER; tests for the login screen and for other accounts change it.
"""
import pytest
import streamlit as st
import streamlit.user_info

from auth_helpers import TEST_USER


@pytest.fixture(autouse=True)
def app_user(monkeypatch):
    """The claims st.user returns. Mutate it (or use sign_in_as) to change who is signed in."""
    user = {"is_logged_in": True, **TEST_USER}
    monkeypatch.setattr(streamlit.user_info, "_get_user_info", lambda: user)

    def fake_logout():
        # st.logout() clears the session's user info and reruns; there is no OIDC provider to call here.
        user.clear()
        user["is_logged_in"] = False
        st.rerun()

    monkeypatch.setattr(st, "logout", fake_logout)
    return user


@pytest.fixture
def sign_in_as(app_user):
    """Replace the simulated user, e.g. sign_in_as(None) for a visitor who has not logged in."""
    def _sign_in_as(claims):
        app_user.clear()
        app_user["is_logged_in"] = claims is not None
        app_user.update(claims or {})
    return _sign_in_as
