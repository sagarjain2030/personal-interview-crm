"""Database tests for Google account registration and lookup (multi-user support)."""
import sqlite3
import threading
import uuid

import pytest

import db
from auth_helpers import OTHER_USER, TEST_USER


def test_first_sign_in_creates_a_user(fetch_rows):
    user_id = db.get_or_create_user(TEST_USER["sub"], TEST_USER["email"], TEST_USER["name"])

    uuid.UUID(user_id)
    rows = fetch_rows("SELECT id, google_sub, email, name, created_at FROM users")
    assert len(rows) == 1
    assert rows[0][:4] == (user_id, TEST_USER["sub"], TEST_USER["email"], TEST_USER["name"])
    assert rows[0][4]  # created_at


def test_existing_user_is_returned_without_duplicates(fetch_rows):
    first = db.get_or_create_user(TEST_USER["sub"], TEST_USER["email"], TEST_USER["name"])
    again = [db.get_or_create_user(TEST_USER["sub"], TEST_USER["email"], TEST_USER["name"]) for _ in range(3)]
    assert again == [first] * 3
    assert fetch_rows("SELECT count(*) FROM users") == [(1,)]


def test_profile_changes_update_the_same_user(fetch_rows):
    user_id = db.get_or_create_user(TEST_USER["sub"], "old@example.com", "Old Name")
    assert db.get_or_create_user(TEST_USER["sub"], "new@example.com", "New Name") == user_id
    assert fetch_rows("SELECT id, email, name FROM users") == [(user_id, "new@example.com", "New Name")]


def test_missing_profile_claims_do_not_erase_stored_values(fetch_rows):
    user_id = db.get_or_create_user(TEST_USER["sub"], TEST_USER["email"], TEST_USER["name"])
    assert db.get_or_create_user(TEST_USER["sub"]) == user_id
    assert fetch_rows("SELECT email, name FROM users") == [(TEST_USER["email"], TEST_USER["name"])]


def test_different_google_accounts_get_different_users():
    assert db.get_or_create_user(TEST_USER["sub"]) != db.get_or_create_user(OTHER_USER["sub"])


def test_email_is_not_an_identity(fetch_rows):
    """Two accounts with the same email but different `sub` claims are separate users."""
    first = db.get_or_create_user("sub-one", "shared@example.com", "Same Name")
    second = db.get_or_create_user("sub-two", "shared@example.com", "Same Name")
    assert first != second
    assert fetch_rows("SELECT count(*) FROM users") == [(2,)]


@pytest.mark.parametrize("bad_sub", [None, "", "   ", " sub", "sub ", 123, b"bytes-sub", ["sub"],
                                     "x" * 256, "tab\tsub", "new\nline"])
def test_missing_or_invalid_sub_is_rejected(bad_sub, fetch_rows):
    with pytest.raises(db.InvalidIdentityError):
        db.get_or_create_user(bad_sub, "someone@example.com", "Someone")
    assert fetch_rows("SELECT count(*) FROM users") == [(0,)]


def test_longest_allowed_sub_is_accepted():
    assert db.get_or_create_user("9" * db.GOOGLE_SUB_MAX_LENGTH)


@pytest.mark.parametrize("email, name", [(123, ["x"]), ("e" * 400, "n" * 400), ("", "")])
def test_unusable_profile_claims_are_not_stored(email, name, fetch_rows):
    db.get_or_create_user(TEST_USER["sub"], email, name)
    assert fetch_rows("SELECT email, name FROM users") == [(None, None)]


def test_schema_enforces_unique_google_sub(test_db_path):
    db.get_or_create_user(TEST_USER["sub"])
    conn = sqlite3.connect(test_db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO users (id, google_sub, created_at) VALUES (?, ?, ?)",
                         (str(uuid.uuid4()), TEST_USER["sub"], "2026-01-01"))
    finally:
        conn.close()


def test_concurrent_first_sign_ins_create_exactly_one_user(fetch_rows):
    """Many sessions of the same account signing in at once must all get the same single user."""
    thread_count = 16
    barrier = threading.Barrier(thread_count)
    results, errors = [], []

    def sign_in():
        try:
            barrier.wait()
            results.append(db.get_or_create_user(TEST_USER["sub"], TEST_USER["email"], TEST_USER["name"]))
        except Exception as error:  # collected and asserted below
            errors.append(error)

    threads = [threading.Thread(target=sign_in) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(set(results)) == 1 and len(results) == thread_count
    assert fetch_rows("SELECT count(*) FROM users") == [(1,)]
