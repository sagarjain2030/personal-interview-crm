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


