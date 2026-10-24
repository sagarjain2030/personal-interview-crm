"""Shared fixtures and database-safety guards for every test layer.

Safety rules:
1. INTERVIEW_CRM_DB_PATH is set to a throwaway path *before* `db` is imported, so even a
   test that forgets the fixture can never fall back to the real data/interview_crm.db.
2. Every test gets its own fresh SQLite file (the autouse `test_db_path` fixture).
3. A session-wide guard hashes the real database before and after the run and fails loudly if it changed.
"""
import hashlib
import os
import pathlib
import shutil
import sqlite3
import tempfile

import pytest

PROJECT_DIR = pathlib.Path(__file__).resolve().parent.parent
REAL_DB_PATH = PROJECT_DIR / "data" / "interview_crm.db"

_SESSION_DIR = pathlib.Path(tempfile.mkdtemp(prefix="crm_tests_"))
os.environ["INTERVIEW_CRM_DB_PATH"] = str(_SESSION_DIR / "fallback.db")

import db  # noqa: E402  (must be imported after the environment override above)
from auth_helpers import OTHER_USER, TEST_USER  # noqa: E402


def _file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


@pytest.fixture(scope="session", autouse=True)
def real_database_guard():
    """Fail the run if the real database file is created, modified or deleted."""
    assert pathlib.Path(db.DB_PATH).resolve() != REAL_DB_PATH.resolve()
    hash_before = _file_hash(REAL_DB_PATH)
    yield
    shutil.rmtree(_SESSION_DIR, ignore_errors=True)
    assert _file_hash(REAL_DB_PATH) == hash_before, "The real database changed during testing!"


@pytest.fixture(autouse=True)
def test_db_path(tmp_path, monkeypatch):
    """Point the app at a fresh, schema-initialised database inside this test's temp folder."""
    path = tmp_path / "data" / "interview_crm.db"
    assert path.resolve() != REAL_DB_PATH.resolve()
    monkeypatch.setattr(db, "DB_PATH", path)
    monkeypatch.setenv("INTERVIEW_CRM_DB_PATH", str(path))
    db.init_db()
    return path


@pytest.fixture
def fetch_rows(test_db_path):
    """Run a read-only SQL query against the test database and return all rows."""
    def _fetch(sql, params=()):
        conn = sqlite3.connect(test_db_path)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()
    return _fetch


@pytest.fixture
def owner_id(test_db_path):
    """Internal user id of TEST_USER (the default signed-in test account), registered as on first login."""
    return db.get_or_create_user(TEST_USER["sub"], TEST_USER["email"], TEST_USER["name"])


@pytest.fixture
def other_user_id(test_db_path):
    """Internal user id of OTHER_USER, a second, unrelated Google account."""
    return db.get_or_create_user(OTHER_USER["sub"], OTHER_USER["email"], OTHER_USER["name"])


@pytest.fixture
def seeded(owner_id):
    """Two applications (A, B) of TEST_USER with interview rounds and one question, created through db.py."""
    app_a = db.create_application(owner_id, "Acme Corp", "Python Developer", notes="seeded")
    app_b = db.create_application(owner_id, "Globex", "Data Engineer")
    a_round1 = db.create_interview(owner_id, app_a, 1, 1)
    a_round2 = db.create_interview(owner_id, app_a, 2, 2)
    b_round1 = db.create_interview(owner_id, app_b, 1, 3)
    a1_question = db.create_interview_question(owner_id, a_round1, "What is a Python decorator?",
                                               "A wrapper function.")
    return {
        "app_a": app_a, "app_b": app_b,
        "a_round1": a_round1, "a_round2": a_round2, "b_round1": b_round1,
        "a1_question": a1_question,
    }
