"""backup_db.py: online backups are complete and verifiable, and restoring one gives a working database."""
import os
import shutil
import sqlite3

import pytest

import backup_db
import db


@pytest.fixture
def populated(owner_id, other_user_id):
    app_id = db.create_application(owner_id, "Backup Co", "Role", notes="dummy")
    interview_id = db.create_interview(owner_id, app_id, 1, 2)
    db.create_interview_question(owner_id, interview_id, "Dummy question?")
    db.create_resume_version(other_user_id, "Dummy CV")
    return {"owner": owner_id, "other": other_user_id, "app": app_id}


def all_rows(path):
    conn = sqlite3.connect(path)
    try:
        return {t: conn.execute(f"SELECT * FROM {t} ORDER BY rowid").fetchall()
                for t in ["users", "resume_versions", "applications", "interviews", "interview_questions"]}
    finally:
        conn.close()


def test_backup_is_complete_verified_and_private(populated, test_db_path, tmp_path):
    destination = backup_db.backup(tmp_path / "crm.db")
    assert all_rows(destination) == all_rows(test_db_path)
    assert backup_db.verify(destination) == {"applications": 1, "interview_questions": 1, "interviews": 1,
                                             "resume_versions": 1, "users": 2}
    assert oct(destination.stat().st_mode & 0o777) == "0o600"
    assert not destination.with_name(destination.name + "-wal").exists()  # self-contained single file


def test_missing_destination_directory_is_created_private(populated, tmp_path):
    destination = backup_db.backup(tmp_path / "backups" / "crm.db")
    assert backup_db.verify(destination)["applications"] == 1
    assert oct(destination.parent.stat().st_mode & 0o777) == "0o700"


def test_default_destination_is_timestamped_next_to_the_database(populated, test_db_path):
    destination = backup_db.backup()
    assert destination.parent == test_db_path.parent.resolve()
    assert destination.name.startswith("interview_crm.backup-") and destination.suffix == ".db"


def test_backup_includes_commits_still_in_the_wal_while_the_app_is_running(populated, test_db_path, tmp_path):
    app = sqlite3.connect(test_db_path)  # an open app connection prevents the WAL from being checkpointed away
    try:
        app.execute("SELECT count(*) FROM users").fetchall()  # holds the WAL open, like a live app session
        db.create_application(populated["owner"], "Only In WAL Co", "Role")
        assert os.path.getsize(f"{test_db_path}-wal") > 0
        naive_copy = tmp_path / "naive.db"
        shutil.copyfile(test_db_path, naive_copy)  # what a plain file copy would capture
        destination = backup_db.backup(tmp_path / "online.db")
    finally:
        app.close()
    companies = {r[0] for r in sqlite3.connect(destination).execute("SELECT company FROM applications")}
    assert "Only In WAL Co" in companies
    naive = {r[0] for r in sqlite3.connect(naive_copy).execute("SELECT company FROM applications")}
    assert "Only In WAL Co" not in naive  # why backup_db.py exists


def test_restored_backup_works_with_the_app_and_keeps_isolation(populated, tmp_path, monkeypatch):
    destination = backup_db.backup(tmp_path / "crm.db")
    restored = tmp_path / "restored" / "interview_crm.db"
    restored.parent.mkdir()
    shutil.copyfile(destination, restored)
    monkeypatch.setattr(db, "DB_PATH", restored)

    db.init_db()  # app start-up on a restored current backup: no migration, no changes
    assert db.get_or_create_user("test-user-google-sub") == populated["owner"]
    assert [r[0] for r in db.get_all_applications(populated["owner"])] == [populated["app"]]
    assert db.get_application_by_id(populated["other"], populated["app"]) is None
    assert len(db.get_resume_versions(populated["other"])) == 1


def test_backup_never_overwrites(populated, test_db_path, tmp_path):
    existing = tmp_path / "existing.db"
    existing.write_bytes(b"keep me")
    for destination in (existing, test_db_path):
        with pytest.raises(backup_db.BackupError, match="Refusing to overwrite"):
            backup_db.backup(destination)
    assert existing.read_bytes() == b"keep me"


def test_missing_source_is_an_error_and_is_not_created(tmp_path, monkeypatch):
    missing = tmp_path / "nowhere" / "interview_crm.db"
    monkeypatch.setattr(db, "DB_PATH", missing)
    with pytest.raises(backup_db.BackupError, match="does not exist"):
        backup_db.backup(tmp_path / "out.db")
    assert not missing.exists() and not (tmp_path / "out.db").exists()


def test_verify_rejects_bad_files(populated, tmp_path, test_db_path):
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a database" * 200)
    with pytest.raises(backup_db.BackupError, match="Not a readable SQLite database"):
        backup_db.verify(corrupt)

    with pytest.raises(backup_db.BackupError, match="does not exist"):
        backup_db.verify(tmp_path / "absent.db")

    old_version = backup_db.backup(tmp_path / "old.db")
    sqlite3.connect(old_version).execute("PRAGMA user_version = 0")
    with pytest.raises(backup_db.BackupError, match="Schema version is 0"):
        backup_db.verify(old_version)

    broken_fk = backup_db.backup(tmp_path / "fk.db")
    conn = sqlite3.connect(broken_fk)
    conn.execute("INSERT INTO interviews (id, application_id) VALUES ('orphan', 'missing')")
    conn.commit()
    conn.close()
    with pytest.raises(backup_db.BackupError, match="Foreign key"):
        backup_db.verify(broken_fk)


def test_cli_exit_codes_and_output_contain_no_record_data(populated, tmp_path, capsys):
    assert backup_db.main(["backup", str(tmp_path / "cli.db")]) == 0
    assert backup_db.main(["verify", str(tmp_path / "cli.db")]) == 0
    assert backup_db.main(["verify", str(tmp_path / "missing.db")]) == 1
    output = capsys.readouterr()
    assert "applications: 1 rows" in output.out and "FAILED" in output.err
    assert "Backup Co" not in output.out + output.err and "Dummy" not in output.out + output.err
