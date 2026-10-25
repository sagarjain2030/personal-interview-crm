"""Online backup and verification of the CRM's SQLite database (standard library only).

    python backup_db.py backup [DESTINATION]   # consistent copy of INTERVIEW_CRM_DB_PATH, safe while the app runs
    python backup_db.py verify FILE            # check a backup (or a restored copy) before relying on it

The database runs in WAL mode, so copying only the .db file while the app is running can miss recent
commits that are still in the -wal file. SQLite's backup API always produces a complete snapshot.
Output is limited to checks and row counts; record contents are never printed.
"""
import argparse
import os
import pathlib
import sqlite3
import sys
from datetime import datetime, timezone

import db


class BackupError(Exception):
    pass


def _expected_schema():
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(db.SCHEMA_PATH.read_text(encoding="utf-8"))
        return _schema(conn)
    finally:
        conn.close()


def _schema(conn):
    return sorted(conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))


def verify(path):
    """Check integrity, foreign keys, schema version and schema; return {table: row count}."""
    path = pathlib.Path(path)
    if not path.is_file():
        raise BackupError(f"{path} does not exist.")
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise BackupError("Integrity check failed.")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise BackupError("Foreign key check failed.")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version != db.SCHEMA_VERSION:
                raise BackupError(f"Schema version is {version}, expected {db.SCHEMA_VERSION}.")
            if _schema(conn) != _expected_schema():
                raise BackupError("Schema does not match schema.sql.")
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {table: conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] for table in tables}
        finally:
            conn.close()
    except sqlite3.DatabaseError as error:
        raise BackupError(f"Not a readable SQLite database ({error}).") from None


def backup(destination=None):
    """Write a consistent, self-contained copy of the live database and verify it. Returns its path."""
    source = pathlib.Path(db.DB_PATH).resolve()
    if not source.is_file():
        raise BackupError(f"Database {source} does not exist.")
    if destination is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = source.with_name(f"{source.stem}.backup-{timestamp}.db")
    destination = pathlib.Path(destination).resolve()
    if destination == source or destination.exists():
        raise BackupError(f"Refusing to overwrite {destination}.")

    # mode=ro: never writes to (or creates) the live database.
    src = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
    old_umask = os.umask(0o077)  # the backup holds private records: owner-only permissions
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)  # e.g. a first backup into /data/backups/
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode = DELETE")  # one self-contained file, no -wal/-shm
        finally:
            dst.close()
    finally:
        os.umask(old_umask)
        src.close()
    verify(destination)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup", help="back up INTERVIEW_CRM_DB_PATH").add_argument("destination", nargs="?")
    commands.add_parser("verify", help="verify a backup file").add_argument("file")
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            path = backup(args.destination)
            print(f"Backup written: {path}")
        else:
            path = pathlib.Path(args.file)
        counts = verify(path)
    except BackupError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    print("Verified: integrity ok, foreign keys ok, schema version", db.SCHEMA_VERSION)
    for table, count in counts.items():
        print(f"  {table}: {count} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
