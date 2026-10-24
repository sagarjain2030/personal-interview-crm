"""Build a database exactly as the single-user version (schema version 0) created it, for migration tests."""
import sqlite3

# schema.sql before multi-user support, verbatim.
LEGACY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS resume_versions (id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL, file_path TEXT, notes TEXT, created_at TEXT NOT NULL );

CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY NOT NULL, company TEXT NOT NULL, role TEXT NOT NULL, raw_job_description TEXT, jd_url TEXT, location TEXT, notes TEXT, created_at TEXT NOT NULL, applied_date TEXT, status INT NOT NULL DEFAULT 0, resume_version_id TEXT, priority INT NOT NULL DEFAULT 2, jd_analysis_json TEXT, jd_analysis_status INT NOT NULL DEFAULT 0, FOREIGN KEY (resume_version_id) REFERENCES resume_versions(id), CHECK (status BETWEEN 0 AND 6), CHECK (priority BETWEEN 1 AND 3), CHECK (jd_analysis_status BETWEEN 0 AND 2));

CREATE TABLE IF NOT EXISTS interviews (id TEXT PRIMARY KEY NOT NULL, application_id TEXT NOT NULL, round_type INT NOT NULL DEFAULT 0, round_number INT NOT NULL DEFAULT 1, interview_date TEXT, interviewer TEXT, result INT NOT NULL DEFAULT 0,confidence INT NOT NULL DEFAULT 0, notes TEXT, ai_analysis_status INT NOT NULL DEFAULT 0, ai_analysis TEXT, FOREIGN KEY (application_id) REFERENCES applications(id), CHECK (round_type BETWEEN 0 AND 4), CHECK (round_number >= 1), CHECK (result BETWEEN 0 AND 3), CHECK (confidence BETWEEN 0 AND 5), CHECK (ai_analysis_status BETWEEN 0 AND 2));

CREATE TABLE IF NOT EXISTS interview_questions (id TEXT PRIMARY KEY NOT NULL, interview_id TEXT NOT NULL, question TEXT NOT NULL, topic TEXT, subtopic TEXT, apparent_answer TEXT, better_answer TEXT, missing_concept TEXT, priority INT NOT NULL DEFAULT 2,  FOREIGN KEY (interview_id) REFERENCES interviews(id), CHECK (priority BETWEEN 1 AND 3));

CREATE INDEX IF NOT EXISTS id_applications_resume_version_id on applications(resume_version_id);

CREATE INDEX IF NOT EXISTS id_interviews_application_id on interviews(application_id);

CREATE INDEX IF NOT EXISTS id_interview_questions_interview_id on interview_questions(interview_id);
"""

LEGACY_IDS = {
    "resume": "00000000-0000-4000-8000-000000000001",
    "app_a": "00000000-0000-4000-8000-0000000000a1",
    "app_b": "00000000-0000-4000-8000-0000000000b1",
    "a_round1": "00000000-0000-4000-8000-0000000001a1",
    "a1_question": "00000000-0000-4000-8000-0000000002a1",
}

# Every row, with every column, so a migration test can prove nothing was lost or altered.
LEGACY_ROWS = {
    "resume_versions": [(LEGACY_IDS["resume"], "Backend CV v3", "cv/backend_v3.pdf", "tailored", "2026-10-01T09:00:00+00:00")],
    "applications": [
        (LEGACY_IDS["app_a"], "Legacy Corp", "Python Developer", "JD text\nline 2", "https://example.com/a",
         "Remote", "legacy notes", "2026-10-02T09:00:00+00:00", "2026-10-03", 1, LEGACY_IDS["resume"], 3,
         '{"skills": ["python"]}', 2),
        (LEGACY_IDS["app_b"], "Old Globex", "Data Engineer", None, None, None, None,
         "2026-10-04T09:00:00+00:00", None, 0, None, 2, None, 0),
    ],
    "interviews": [(LEGACY_IDS["a_round1"], LEGACY_IDS["app_a"], 2, 1, "2026-10-05", "Jane", 1, 4, "went well", 0, None)],
    "interview_questions": [(LEGACY_IDS["a1_question"], LEGACY_IDS["a_round1"], "What is the GIL?", "concurrency",
                             "threads", "A lock.", "A mutex in CPython.", "free-threading", 3)],
}


def create_legacy_db(path, with_data=True):
    """Create a version-0 database at `path` (replacing any file there) and return the rows it holds."""
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(LEGACY_SCHEMA_SQL)
        if with_data:
            for table, rows in LEGACY_ROWS.items():
                for row in rows:
                    conn.execute(f"INSERT INTO {table} VALUES ({', '.join('?' * len(row))})", row)
        conn.commit()
    finally:
        conn.close()
    return LEGACY_ROWS if with_data else {}
