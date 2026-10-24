"""UI Test — Google login gate, single-user authorization and Logout in a real Chromium browser."""
import re

import pytest
from playwright.sync_api import expect

import db
from auth_helpers import AUTHORIZED_USER, UNAUTHORIZED_USER, sign_in
from ui_helpers import wait_until_idle, wait_until_login_screen

pytestmark = pytest.mark.e2e


def expect_crm_hidden(page):
    expect(page.get_by_role("radiogroup", name="Navigation")).to_have_count(0)
    expect(page.get_by_role("button", name="Logout")).to_have_count(0)
    expect(page.get_by_role("button", name="Save Application")).to_have_count(0)
    expect(page.get_by_text("Acme Corp")).to_have_count(0)


def test_visitor_sees_only_login_screen(login_page):
    db.create_application("Acme Corp", "Python Developer")
    login_page.reload()
    wait_until_login_screen(login_page)
    expect(login_page.get_by_role("heading", name="Personal Interview CRM", level=1)).to_be_visible()
    expect_crm_hidden(login_page)


def test_sign_in_button_starts_google_login(login_page):
    # Stop at Streamlit's own login route so the test never reaches Google.
    login_page.route(re.compile(r".*/auth/login.*"), lambda route: route.fulfill(body="login started"))
    login_page.get_by_role("button", name="Sign in with Google").click()
    expect(login_page).to_have_url(re.compile(r"/auth/login\?provider="))


def test_unauthorized_google_account_is_denied(page, app_server):
    db.create_application("Acme Corp", "Python Developer")
    sign_in(page.context, app_server.url, UNAUTHORIZED_USER)
    page.goto(app_server.url)
    expect(page.get_by_text("Access Denied")).to_be_visible()
    wait_until_idle(page)
    expect_crm_hidden(page)
    expect(page.get_by_text(UNAUTHORIZED_USER["name"])).to_have_count(0)


def test_forged_session_cookie_is_rejected(page, app_server):
    sign_in(page.context, app_server.url, AUTHORIZED_USER, cookie_secret="attacker-guessed-secret")
    page.goto(app_server.url)
    wait_until_login_screen(page)
    expect_crm_hidden(page)


def test_authorized_owner_sees_name_logout_and_crm(app):
    expect(app.get_by_text(AUTHORIZED_USER["name"], exact=True)).to_be_visible()
    expect(app.get_by_role("button", name="Logout")).to_be_visible()
    expect(app.get_by_role("radiogroup", name="Navigation")).to_be_visible()
    expect(app.get_by_text(AUTHORIZED_USER["sub"])).to_have_count(0)
    expect(app.get_by_text(AUTHORIZED_USER["email"])).to_have_count(0)


def test_logout_returns_to_login_screen_and_stays_logged_out(app):
    app.get_by_role("button", name="Logout").click()
    wait_until_login_screen(app)
    expect_crm_hidden(app)
    app.reload()  # the session cookie was cleared, so a refresh must not sign back in
    wait_until_login_screen(app)
    expect_crm_hidden(app)
