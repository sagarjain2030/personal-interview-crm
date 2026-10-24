-- Schema version 1 (multi-user). db.init_db() creates it on a fresh database and rebuilds a
-- version-0 (single-user) database into it. Keep both paths in mind when changing this file.
--
-- Ownership: users own applications and resume_versions directly (user_id). Interviews and
-- interview_questions are owned through their parent application; db.py checks the whole chain.

CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY NOT NULL, google_sub TEXT NOT NULL UNIQUE, email TEXT, name TEXT, created_at TEXT NOT NULL);

-- UNIQUE (id, user_id) is the parent key for the composite foreign key on applications.
CREATE TABLE IF NOT EXISTS resume_versions (id TEXT PRIMARY KEY NOT NULL, user_id TEXT NOT NULL, name TEXT NOT NULL, file_path TEXT, notes TEXT, created_at TEXT NOT NULL, FOREIGN KEY (user_id) REFERENCES users(id), UNIQUE (id, user_id));

-- (resume_version_id, user_id) -> resume_versions(id, user_id): an application can only use a resume of the same user.
CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY NOT NULL, user_id TEXT NOT NULL, company TEXT NOT NULL, role TEXT NOT NULL, raw_job_description TEXT, jd_url TEXT, location TEXT, notes TEXT, created_at TEXT NOT NULL, applied_date TEXT, status INT NOT NULL DEFAULT 0, resume_version_id TEXT, priority INT NOT NULL DEFAULT 2, jd_analysis_json TEXT, jd_analysis_status INT NOT NULL DEFAULT 0, FOREIGN KEY (user_id) REFERENCES users(id), FOREIGN KEY (resume_version_id, user_id) REFERENCES resume_versions(id, user_id), CHECK (status BETWEEN 0 AND 6), CHECK (priority BETWEEN 1 AND 3), CHECK (jd_analysis_status BETWEEN 0 AND 2));

CREATE TABLE IF NOT EXISTS interviews (id TEXT PRIMARY KEY NOT NULL, application_id TEXT NOT NULL, round_type INT NOT NULL DEFAULT 0, round_number INT NOT NULL DEFAULT 1, interview_date TEXT, interviewer TEXT, result INT NOT NULL DEFAULT 0,confidence INT NOT NULL DEFAULT 0, notes TEXT, ai_analysis_status INT NOT NULL DEFAULT 0, ai_analysis TEXT, FOREIGN KEY (application_id) REFERENCES applications(id), CHECK (round_type BETWEEN 0 AND 4), CHECK (round_number >= 1), CHECK (result BETWEEN 0 AND 3), CHECK (confidence BETWEEN 0 AND 5), CHECK (ai_analysis_status BETWEEN 0 AND 2));

CREATE TABLE IF NOT EXISTS interview_questions (id TEXT PRIMARY KEY NOT NULL, interview_id TEXT NOT NULL, question TEXT NOT NULL, topic TEXT, subtopic TEXT, apparent_answer TEXT, better_answer TEXT, missing_concept TEXT, priority INT NOT NULL DEFAULT 2,  FOREIGN KEY (interview_id) REFERENCES interviews(id), CHECK (priority BETWEEN 1 AND 3));

CREATE INDEX IF NOT EXISTS id_resume_versions_user_id on resume_versions(user_id);

CREATE INDEX IF NOT EXISTS id_applications_user_id_created_at on applications(user_id, created_at);

CREATE INDEX IF NOT EXISTS id_applications_resume_version_id on applications(resume_version_id, user_id);

CREATE INDEX IF NOT EXISTS id_interviews_application_id on interviews(application_id);

CREATE INDEX IF NOT EXISTS id_interview_questions_interview_id on interview_questions(interview_id);
