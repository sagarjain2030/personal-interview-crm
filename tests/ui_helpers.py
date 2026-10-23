"""Playwright helpers for driving the real Streamlit UI through accessible roles and visible text."""
import csv
import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect


def wait_until_idle(page):
    """Wait until Streamlit has finished running the script.

    Streamlit exposes its run state on the app root (it uses this attribute in its own e2e tests).
    Interacting while the first run is still in progress can be lost (e.g. a dropdown that closes again).
    """
    expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")


def wait_until_loaded(page):
    expect(page.get_by_role("heading", name="Personal Interview CRM", level=1)).to_be_visible()
    wait_until_idle(page)


def open_section(page, section):
    """Click a sidebar navigation option and wait for that page's header."""
    page.get_by_role("radiogroup", name="Navigation").get_by_text(section, exact=True).click()
    expect(page.get_by_role("heading", name=section, exact=True, level=2)).to_be_visible()
    wait_until_idle(page)


def refresh(page):
    """Browser refresh (F5): starts a new Streamlit session on the same server."""
    page.reload()
    wait_until_loaded(page)


def dropdown(page, label):
    return page.get_by_role("combobox", name=label)


def open_dropdown(page, label):
    """Open a selectbox and return its option list.

    Right after page load or a form submit, the first click on a Streamlit selectbox can only
    focus it without opening the menu. A user would then click again or press a key; we press
    ArrowDown, which opens a focused select.
    """
    wait_until_idle(page)
    box = dropdown(page, label)
    listbox = page.get_by_role("listbox")
    box.click()
    for _ in range(3):
        try:
            expect(listbox).to_be_visible(timeout=2_000)
            return listbox
        except AssertionError:
            box.press("ArrowDown")
    raise AssertionError(f"dropdown {label!r} did not open")


def choose(page, label, option):
    """Open a Streamlit selectbox and pick the option with exactly this visible text.

    If a rerun triggered by the previous action finishes while the menu is open, Streamlit
    re-renders the selectbox and the menu closes; in that case open it again and retry.
    """
    for _ in range(3):
        listbox = open_dropdown(page, label)
        try:
            listbox.get_by_role("option", name=option, exact=True).click(timeout=3_000)
            break
        except PlaywrightError:
            page.keyboard.press("Escape")
    else:
        raise AssertionError(f"could not choose {option!r} in dropdown {label!r}")
    expect(dropdown(page, label)).to_have_value(option)
    wait_until_idle(page)


def dropdown_options(page, label):
    """Return the visible option texts of a selectbox (opens and closes it)."""
    options = open_dropdown(page, label).get_by_role("option")
    expect(options.first).to_be_visible()
    values = options.all_inner_texts()
    page.keyboard.press("Escape")
    return values


def button(page, name):
    return page.get_by_role("button", name=name, exact=True)


def read_table(page):
    """Read the page's st.dataframe through its own 'Download as CSV' toolbar button.

    The grid is drawn on a <canvas>, so the CSV export is the reliable way to read what is displayed.
    """
    table = page.get_by_test_id("stDataFrame")
    # Centre the table (away from Streamlit's sticky header) and hover it to show its toolbar.
    table.evaluate("element => element.scrollIntoView({block: 'center'})")
    table.hover()
    # Activate the button with the keyboard: the grid's overlay can intercept mouse clicks.
    with page.expect_download(timeout=5_000) as download_info:
        button(page, "Download as CSV").press("Enter", timeout=5_000)
    with open(download_info.value.path(), encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def wait_for_table(page, condition, timeout=20):
    """Re-read the table until `condition(rows)` is true.

    During a Streamlit rerun the table may briefly show old data or be replaced while we read it,
    so a failed read just means "not ready yet" and is retried until the deadline.
    """
    deadline = time.monotonic() + timeout
    rows, last_error = [], None
    while time.monotonic() < deadline:
        try:
            rows = read_table(page)
        except PlaywrightError as error:
            last_error = error
            continue
        if condition(rows):
            return rows
    raise AssertionError(f"table never satisfied the condition; last rows: {rows}; last error: {last_error}")


def expect_no_app_errors(page):
    """No Python exception boxes and no app-level 'Failed to ...' messages are visible."""
    expect(page.get_by_test_id("stException")).to_have_count(0)
    expect(page.get_by_text("Traceback")).to_have_count(0)
    expect(page.get_by_text("Failed to")).to_have_count(0)
