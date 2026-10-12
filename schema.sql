CREATE TABLE IF NOT EXISTS resume_versions (id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL, file_path TEXT, notes TEXT, created_at TEXT NOT NULL );

CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY NOT NULL, company TEXT NOT NULL, role TEXT NOT NULL, raw_job_description TEXT, jd_url TEXT, location TEXT, notes TEXT, created_at TEXT NOT NULL, applied_date TEXT, status INT NOT NULL DEFAULT 0, resume_version_id TEXT, priority INT NOT NULL DEFAULT 2, jd_analysis_json TEXT, jd_analysis_status INT NOT NULL DEFAULT 0, FOREIGN KEY (resume_version_id) REFERENCES resume_versions(id), CHECK (status BETWEEN 0 AND 6), CHECK (priority BETWEEN 1 AND 3), CHECK (jd_analysis_status BETWEEN 0 AND 2));

CREATE TABLE IF NOT EXISTS interviews (id TEXT PRIMARY KEY NOT NULL, application_id TEXT NOT NULL, round_type INT NOT NULL DEFAULT 0, round_number INT NOT NULL DEFAULT 1, interview_date TEXT, interviewer TEXT, result INT NOT NULL DEFAULT 0,confidence INT NOT NULL DEFAULT 0, notes TEXT, ai_analysis_status INT NOT NULL DEFAULT 0, ai_analysis TEXT, FOREIGN KEY (application_id) REFERENCES applications(id), CHECK (round_type BETWEEN 0 AND 4), CHECK (round_number >= 1), CHECK (result BETWEEN 0 AND 3), CHECK (confidence BETWEEN 0 AND 5), CHECK (ai_analysis_status BETWEEN 0 AND 2));

CREATE TABLE IF NOT EXISTS interview_questions (id TEXT PRIMARY KEY NOT NULL, interview_id TEXT NOT NULL, question TEXT NOT NULL, topic TEXT, subtopic TEXT, apparent_answer TEXT, better_answer TEXT, missing_concept TEXT, priority INT NOT NULL DEFAULT 2,  FOREIGN KEY (interview_id) REFERENCES interviews(id), CHECK (priority BETWEEN 1 AND 3));

CREATE INDEX IF NOT EXISTS id_applications_resume_version_id on applications(resume_version_id);

CREATE INDEX IF NOT EXISTS id_interviews_application_id on interviews(application_id);

CREATE INDEX IF NOT EXISTS id_interview_questions_interview_id on interview_questions(interview_id);

