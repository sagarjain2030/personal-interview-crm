import sqlite3 as sql
import pathlib
import uuid
from datetime import datetime, timezone

BASE_DIR = pathlib.Path(__file__).parent.absolute()
SCHEMA_PATH =  pathlib.Path(BASE_DIR, 'schema.sql')
DB_PATH = pathlib.Path(BASE_DIR, 'data/interview_crm.db')

def get_connection():
    conn = sql.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    pathlib.Path(DB_PATH.parent).mkdir(parents=True, exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        conn.executescript(schema_sql)
    finally:
        conn.close()


def create_application(
    company,
    role,
    raw_job_description=None,
    jd_url=None,
     location=None,
    notes=None
):
    application_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    insert_stmt = """
        INSERT INTO applications (id,company,role,raw_job_description,
            jd_url,location,notes,created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    conn = get_connection()
    try:
        conn.execute(
            insert_stmt,(application_id,company,role,raw_job_description,
                jd_url,location,notes,created_at))
        conn.commit()
    finally:
        conn.close()
    return application_id


def get_all_applications():
    conn = get_connection()
    try:
        ret = conn.execute("SELECT id,company,role,status,created_at "
                           "FROM applications ORDER BY created_at DESC ")
        record_data = ret.fetchall()
    finally:
        conn.close()
    return record_data

def get_application_by_id(application_id):
    conn = get_connection()
    try:
        ret = conn.execute("SELECT * FROM applications WHERE id=?",
                           (application_id,))
        record_data = ret.fetchone()
    finally:
        conn.close()
    return record_data

def update_application_status(application_id, new_status):
    conn = get_connection()
    try:
        conn.execute("UPDATE applications SET status = ? WHERE id=?",(new_status, application_id))
        conn.commit()
    finally:
        conn.close()

def update_application_priority(application_id, new_priority):
    conn = get_connection()
    try:
        conn.execute("UPDATE applications SET priority = ? WHERE id=?",(new_priority, application_id))
        conn.commit()
    finally:
        conn.close()

def update_application_details(application_id,  company, role, raw_job_description, jd_url, location, notes):
    conn = get_connection()
    try:
        conn.execute("UPDATE applications SET company = ?, role = ?,"
                     " raw_job_description = ?, jd_url = ?, location = ?, "
                     "notes = ? WHERE id = ?", (company, role, raw_job_description, jd_url, location, notes, application_id))
        conn.commit()
    finally:
        conn.close()