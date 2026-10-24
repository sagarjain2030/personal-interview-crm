"""UI Test — Google login gate, open registration, per-user workspaces and Logout in a real Chromium browser."""
import re

import pytest
from playwright.sync_api import expect

import db
from auth_helpers import OTHER_USER, TEST_USER, sign_in
from ui_helpers import button, open_section, wait_for_table, wait_until_idle, wait_until_loaded, wait_until_login_screen

pytestmark = pytest.mark.e2e


def expect_crm_hidden(page):
    expect(page.get_by_role("radiogroup", name="Navigation")).to_have_count(0)
    expect(page.get_by_role("button", name="Logout")).to_have_count(0)
    expect(page.get_by_role("button", name="Save Application")).to_have_count(0)
    expect(page.get_by_text("Acme Corp")).to_have_count(0)


def test_visitor_sees_only_login_screen(owner_id, login_page):
    db.create_application(owner_id, "Acme Corp", "Python Developer")
    login_page.reload()
    wait_until_login_screen(login_page)
    expect(login_page.get_by_role("heading", name="Personal Interview CRM", level=1)).to_be_visible()
    expect_crm_hidden(login_page)


def test_sign_in_button_starts_google_login(login_page):
    # Stop at Streamlit's own login route so the test never reaches Google.
    login_page.route(re.compile(r".*/auth/login.*"), lambda route: route.fulfill(body="login started"))
    login_page.get_by_role("button", name="Sign in with Google").click()
    expect(login_page).to_have_url(re.compile(r"/auth/login\?provider="))


def test_new_google_account_is_registered_with_an_empty_workspace(owner_id, page, app_server, fetch_rows):
    db.create_application(owner_id, "Acme Corp", "Python Developer")
    sign_in(page.context, app_server.url, OTHER_USER)
    page.goto(app_server.url)
    wait_until_loaded(page)
    expect(page.get_by_text(OTHER_USER["name"], exact=True)).to_be_visible()
    expect(page.get_by_text("No saved applications yet.")).to_be_visible()
    expect(page.get_by_text("Acme Corp")).to_have_count(0)
    assert fetch_rows("SELECT count(*) FROM users WHERE google_sub=?", (OTHER_USER["sub"],)) == [(1,)]


@pytest.mark.parametrize("claims", [{"name": "No Sub"}, {"sub": "", "name": "Empty Sub"}],
                         ids=["missing-sub", "empty-sub"])
def test_signed_cookie_without_a_usable_sub_is_denied(owner_id, page, app_server, claims, fetch_rows):
    db.create_application(owner_id, "Acme Corp", "Python Developer")
    sign_in(page.context, app_server.url, claims)
    page.goto(app_server.url)
    expect(page.get_by_text("Access Denied")).to_be_visible()
    wait_until_idle(page)
    expect_crm_hidden(page)
    assert fetch_rows("SELECT count(*) FROM users") == [(1,)]  # nobody was registered


def test_forged_session_cookie_is_rejected(page, app_server, fetch_rows):
    sign_in(page.context, app_server.url, TEST_USER, cookie_secret="attacker-guessed-secret")
    page.goto(app_server.url)
    wait_until_login_screen(page)
    expect_crm_hidden(page)
    assert fetch_rows("SELECT count(*) FROM users") == [(0,)]


def test_signed_in_user_sees_name_logout_and_crm(app):
    expect(app.get_by_text(TEST_USER["name"], exact=True)).to_be_visible()
    expect(app.get_by_role("button", name="Logout")).to_be_visible()
    expect(app.get_by_role("radiogroup", name="Navigation")).to_be_visible()
    expect(app.get_by_text(TEST_USER["sub"])).to_have_count(0)
    expect(app.get_by_text(TEST_USER["email"])).to_have_count(0)


def test_logout_returns_to_login_screen_and_stays_logged_out(app):
    app.get_by_role("button", name="Logout").click()
    wait_until_login_screen(app)
    expect_crm_hidden(app)
    app.reload()  # the session cookie was cleared, so a refresh must not sign back in
    wait_until_login_screen(app)
    expect_crm_hidden(app)


def test_two_accounts_at_the_same_time_only_see_their_own_data(app, open_new_session, owner_id, other_user_id):
    """Two browsers signed in as different Google accounts on one server; each creates and sees only its own."""
    other = open_new_session(OTHER_USER)

    for page, company in [(app, "Owner Only Co"), (other, "Other Only Co")]:
        page.get_by_label("Company", exact=True).fill(company)
        page.get_by_label("Role", exact=True).fill("Role")
        button(page, "Save Application").click()
        expect(page.get_by_text("Application saved successfully!")).to_be_visible()

    for page, own, foreign in [(app, "Owner Only Co", "Other Only Co"), (other, "Other Only Co", "Owner Only Co")]:
        rows = wait_for_table(page, lambda rows: len(rows) == 1)
        assert rows[0]["Company"] == own
        open_section(page, "Interviews")
        expect(page.get_by_role("combobox", name="Select Application")).to_have_value(f"{own} - Role")
        expect(page.get_by_text(foreign)).to_have_count(0)

    assert [r[1] for r in db.get_all_applications(owner_id)] == ["Owner Only Co"]
    assert [r[1] for r in db.get_all_applications(other_user_id)] == ["Other Only Co"]
