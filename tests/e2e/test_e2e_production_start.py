"""Production start (serve.py, Railway's start command) — secrets from one variable, checked, never printed.

All secrets here are dummies. The server runs exactly as on Railway: `python serve.py` with PORT and
STREAMLIT_SECRETS_TOML set, and no .streamlit/secrets.toml reachable from its HOME.
"""
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
from playwright.sync_api import expect

import serve
from auth_helpers import TEST_COOKIE_SECRET, TEST_USER, sign_in
from ui_helpers import wait_until_loaded, wait_until_login_screen

pytestmark = pytest.mark.e2e

PROJECT_DIR = pathlib.Path(__file__).resolve().parents[2]
DUMMY_CLIENT_SECRET = "dummy-client-secret-value"
DUMMY_AUTH = {
    "redirect_uri": "https://crm.example.com/oauth2callback",
    "cookie_secret": TEST_COOKIE_SECRET,
    "client_id": "dummy-client-id.apps.googleusercontent.com",
    "client_secret": DUMMY_CLIENT_SECRET,
    "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
}


def secrets_toml(**overrides):
    auth = {**DUMMY_AUTH, **overrides}
    return "[auth]\n" + "".join(f'{key} = "{value}"\n' for key, value in auth.items() if value is not None)


def run_serve(env_overrides, tmp_path, port, **popen_args):
    env = {key: value for key, value in os.environ.items() if key != serve.SECRETS_VARIABLE}
    # TMPDIR: the secrets file serve.py writes lands in this test's temp folder and is removed with it.
    env.update({"PORT": str(port), "HOME": str(tmp_path), "TMPDIR": str(tmp_path), **env_overrides})
    popen_args = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "text": True, **popen_args}
    return subprocess.Popen([sys.executable, str(PROJECT_DIR / "serve.py")], cwd=PROJECT_DIR, env=env, **popen_args)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.parametrize("text, message", [
    ('[auth\nclient_id = "x"', "not valid TOML"),
    ('[access]\nallowed_google_sub = ""\n', "no [auth] section"),
    (secrets_toml(client_secret=None, client_id=" "), "missing or has empty: client_id, client_secret"),
    (secrets_toml(redirect_uri="http://localhost:8501/oauth2callback"), "redirect_uri must be https://"),
    (secrets_toml(cookie_secret="short-secret"), "cookie_secret must be at least 32"),
], ids=["invalid-toml", "no-auth", "missing-keys", "http-redirect", "short-cookie-secret"])
def test_unusable_secrets_are_rejected_with_safe_messages(text, message):
    with pytest.raises(serve.ConfigError, match=message.replace("[", r"\[")) as error:
        serve.check_secrets(text)
    assert DUMMY_CLIENT_SECRET not in str(error.value) and TEST_COOKIE_SECRET not in str(error.value)


@pytest.mark.parametrize("value", [None, secrets_toml(redirect_uri="http://crm.example.com/oauth2callback")],
                         ids=["variable-unset", "invalid-secrets"])
def test_serve_refuses_to_start_and_prints_no_secrets(value, tmp_path):
    process = run_serve({} if value is None else {serve.SECRETS_VARIABLE: value}, tmp_path, free_port())
    output, _ = process.communicate(timeout=30)
    assert process.returncode == 1
    assert "The app was not started." in output
    assert DUMMY_CLIENT_SECRET not in output and TEST_COOKIE_SECRET not in output


@pytest.fixture
def production_server(test_db_path, tmp_path):
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    log_path = tmp_path / "serve.log"
    with open(log_path, "w") as log:
        process = run_serve({serve.SECRETS_VARIABLE: secrets_toml(), "INTERVIEW_CRM_DB_PATH": str(test_db_path)},
                            tmp_path, port, stdout=log)
    try:
        deadline = time.monotonic() + 30
        while True:
            assert process.poll() is None, f"serve.py exited early:\n{log_path.read_text()}"
            assert time.monotonic() < deadline, f"serve.py did not become healthy:\n{log_path.read_text()}"
            try:
                with urllib.request.urlopen(f"{url}/_stcore/health", timeout=1) as response:  # Railway's health check
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        yield process, url, log_path
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="inspects the server process through /proc")
def test_production_server_uses_the_variable_secrets_and_keeps_them_private(production_server, page):
    process, url, log_path = production_server

    # serve.py replaced itself with Streamlit (same PID), reading only the private secrets file.
    command = pathlib.Path(f"/proc/{process.pid}/cmdline").read_bytes().split(b"\0")
    secrets_args = [arg.decode() for arg in command if arg.startswith(b"--secrets.files=")]
    assert len(secrets_args) == 1 and b"--client.showErrorDetails=none" in command
    secrets_file = pathlib.Path(secrets_args[0].split("=", 1)[1])
    assert PROJECT_DIR not in secrets_file.parents
    assert oct(secrets_file.stat().st_mode & 0o777) == "0o600"
    assert oct(secrets_file.parent.stat().st_mode & 0o777) == "0o700"
    assert serve.SECRETS_VARIABLE.encode() not in pathlib.Path(f"/proc/{process.pid}/environ").read_bytes()

    # A forged cookie is rejected; one signed with the variable's cookie_secret signs in.
    sign_in(page.context, url, TEST_USER, cookie_secret="attacker-guessed-secret")
    page.goto(url)
    wait_until_login_screen(page)
    page.context.clear_cookies()
    sign_in(page.context, url, TEST_USER)
    page.goto(url)
    wait_until_loaded(page)
    expect(page.get_by_text(TEST_USER["name"], exact=True)).to_be_visible()

    log = log_path.read_text()
    assert DUMMY_CLIENT_SECRET not in log and TEST_COOKIE_SECRET not in log
