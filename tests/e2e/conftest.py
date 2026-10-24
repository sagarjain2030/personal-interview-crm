"""Real-browser fixtures: start a dedicated Streamlit server on the test database and open it in Chromium.

Every test gets its own server process, port and SQLite file (from the autouse `test_db_path`
fixture), so tests never share data and the real database is never touched.

Authentication: each server reads a throwaway secrets file (never .streamlit/secrets.toml) with a
test-only cookie_secret. Signing in sets the same signed `_streamlit_user` cookie that Streamlit
issues after a Google login, so Streamlit's own cookie validation and /auth/logout run unmodified
and Google is never contacted.
"""
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect

from auth_helpers import TEST_USER, auth_secrets, sign_in
from ui_helpers import wait_until_loaded, wait_until_login_screen

PROJECT_DIR = pathlib.Path(__file__).resolve().parents[2]
SERVER_START_TIMEOUT = 30  # seconds

expect.set_options(timeout=15_000)


def _free_port():
    """Ask the OS for an unused local port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_healthy(url, process, log_path):
    deadline = time.monotonic() + SERVER_START_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Streamlit exited early:\n{log_path.read_text()}")
        try:
            with urllib.request.urlopen(f"{url}/_stcore/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)  # polling interval while the server boots, not a fixed wait
    raise RuntimeError(f"Streamlit did not become healthy in {SERVER_START_TIMEOUT}s:\n{log_path.read_text()}")


def _toml_section(name, values):
    return f"[{name}]\n" + "".join(f"{key} = {json.dumps(value)}\n" for key, value in values.items())


def _write_test_secrets(path, url):
    # No [access] section: multi-user mode needs no allowlist, and test databases are always fresh.
    path.write_text(_toml_section("auth", auth_secrets(f"{url}/oauth2callback")))


@pytest.fixture
def app_server(test_db_path, tmp_path):
    """Run `streamlit run main.py` against this test's isolated database and test-only secrets."""
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "INTERVIEW_CRM_DB_PATH": str(test_db_path)}
    log_path = tmp_path / "streamlit.log"
    secrets_path = tmp_path / "secrets.toml"
    _write_test_secrets(secrets_path, url)
    with open(log_path, "w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", str(PROJECT_DIR / "main.py"),
             "--server.headless=true", "--server.address=127.0.0.1", f"--server.port={port}",
             "--browser.gatherUsageStats=false", "--server.fileWatcherType=none",
             f"--secrets.files={secrets_path}"],
            cwd=PROJECT_DIR, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
    try:
        _wait_until_healthy(url, process, log_path)
        yield SimpleNamespace(url=url, db_path=test_db_path, log_path=log_path)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def prepare_page(page, url, wait=wait_until_loaded):
    # Make "Download as CSV" use a normal browser download instead of the native save dialog.
    page.add_init_script("delete window.showSaveFilePicker;")
    page.goto(url)
    wait(page)
    return page


@pytest.fixture
def app(page, app_server):
    """A Chromium page signed in as TEST_USER, with the CRM loaded and ready."""
    sign_in(page.context, app_server.url, TEST_USER)
    return prepare_page(page, app_server.url)


@pytest.fixture
def login_page(page, app_server):
    """A Chromium page for a visitor who has not signed in."""
    return prepare_page(page, app_server.url, wait=wait_until_login_screen)


@pytest.fixture
def open_new_session(browser, app_server):
    """Open the app in a brand-new browser context (separate cookies/session), signed in as TEST_USER
    unless other claims are given."""
    contexts = []

    def _open(claims=TEST_USER):
        context = browser.new_context()
        contexts.append(context)
        sign_in(context, app_server.url, claims)
        return prepare_page(context.new_page(), app_server.url)

    yield _open
    for context in contexts:
        context.close()
