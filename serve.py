"""Production entry point (Railway start command): load secrets from an environment variable, start Streamlit.

    STREAMLIT_SECRETS_TOML='<the complete secrets.toml>' python serve.py

Streamlit reads secrets only from TOML files, and Railway provides service variables, not files. This
writes the variable to a private temporary file outside the repository, checks the [auth] section, and
replaces itself with `streamlit run main.py` reading only that file. Secret values are never printed.
Local development is unchanged: `streamlit run main.py` with .streamlit/secrets.toml.
"""
import os
import sys
import tempfile
import tomllib

SECRETS_VARIABLE = "STREAMLIT_SECRETS_TOML"
REQUIRED_AUTH_KEYS = ("redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url")
MIN_COOKIE_SECRET_LENGTH = 32


class ConfigError(Exception):
    pass


def check_secrets(text):
    """Raise ConfigError (with a message that contains no secret values) if the secrets are unusable."""
    try:
        secrets = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{SECRETS_VARIABLE} is not valid TOML (line {getattr(error, 'lineno', '?')}).") from None
    auth = secrets.get("auth")
    if not isinstance(auth, dict):
        raise ConfigError(f"{SECRETS_VARIABLE} has no [auth] section.")
    missing = [key for key in REQUIRED_AUTH_KEYS if not isinstance(auth.get(key), str) or not auth[key].strip()]
    if missing:
        raise ConfigError(f"[auth] is missing or has empty: {', '.join(missing)}.")
    if not (auth["redirect_uri"].startswith("https://") and auth["redirect_uri"].endswith("/oauth2callback")):
        raise ConfigError("[auth] redirect_uri must be https://<production domain>/oauth2callback.")
    if len(auth["cookie_secret"]) < MIN_COOKIE_SECRET_LENGTH:
        raise ConfigError(f"[auth] cookie_secret must be at least {MIN_COOKIE_SECRET_LENGTH} characters.")


def write_secrets_file(text):
    """Write the secrets to a new owner-only (0600) file in a new owner-only directory and return its path."""
    directory = tempfile.mkdtemp(prefix="crm-secrets-")
    path = os.path.join(directory, "secrets.toml")
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as file:
        file.write(text)
    return path


def streamlit_command(secrets_path, port):
    return [
        sys.executable, "-m", "streamlit", "run", os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"),
        "--server.address=0.0.0.0", f"--server.port={port}", "--server.headless=true",
        "--server.fileWatcherType=none", "--browser.gatherUsageStats=false",
        "--client.showErrorDetails=none",  # tracebacks go to the server log only, never to visitors
        f"--secrets.files={secrets_path}",  # only this file: never a stray ~/.streamlit or repository secrets.toml
    ]


def main():
    text = os.environ.pop(SECRETS_VARIABLE, "")  # not inherited by Streamlit once written to the file
    try:
        if not text.strip():
            raise ConfigError(f"{SECRETS_VARIABLE} is not set.")
        check_secrets(text)
    except ConfigError as error:
        print(f"serve.py: {error} The app was not started.", file=sys.stderr)
        return 1
    command = streamlit_command(write_secrets_file(text), os.environ.get("PORT", "8501"))
    os.execv(command[0], command)


if __name__ == "__main__":
    sys.exit(main())
