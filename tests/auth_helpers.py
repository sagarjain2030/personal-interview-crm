"""Fake Google identities and test-only secrets shared by the AppTest and browser test layers.

None of these values are real: tests never read .streamlit/secrets.toml and never contact Google.
"""
import json

AUTH_COOKIE_NAME = "_streamlit_user"
TEST_USER_SUB = "test-user-google-sub"
OTHER_USER_SUB = "other-user-google-sub"
LEGACY_OWNER_SUB = "test-legacy-owner-google-sub"
TEST_COOKIE_SECRET = "test-only-cookie-secret-not-used-anywhere-else"

# TEST_USER is the account every AppTest and browser test is signed in as unless a test says otherwise.
TEST_USER = {"sub": TEST_USER_SUB, "name": "Test Owner", "email": "owner@example.com"}
OTHER_USER = {"sub": OTHER_USER_SUB, "name": "Someone Else", "email": "other@example.com"}


def auth_secrets(redirect_uri):
    """A complete [auth] section; st.login() is never completed in tests, so the client values are dummies."""
    return {
        "redirect_uri": redirect_uri,
        "cookie_secret": TEST_COOKIE_SECRET,
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
    }


def sign_in(context, url, claims, cookie_secret=TEST_COOKIE_SECRET):
    """Give a Playwright browser context the session cookie Streamlit sets after a successful Google login."""
    from streamlit.web.server.starlette.starlette_app_utils import create_signed_value

    payload = json.dumps({**claims, "origin": url, "is_logged_in": True})
    value = create_signed_value(cookie_secret, AUTH_COOKIE_NAME, payload).decode()
    context.add_cookies([{"name": AUTH_COOKIE_NAME, "value": value, "url": url,
                          "httpOnly": True, "sameSite": "Lax"}])
