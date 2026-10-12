import streamlit as st
from db import create_application
import sqlite3

st.set_page_config(page_title="Personal Interview CRM")

st.title("Personal Interview CRM")

section = st.sidebar.radio(
    "Navigation",
    ["Jobs", "Interviews", "Questions", "Insights"],
)

placeholders = {
    "Jobs": "Saved jobs will appear here in a later step.",
    "Interviews": "Interview records will appear here in a later step.",
    "Questions": "Interview questions will appear here in a later step.",
    "Insights": "Interview insights will appear here in a later step.",
}
st.header(section)
if section == "Jobs":
    with st.form("application_form"):
        company = st.text_input("Company").strip()
        role = st.text_input("Role").strip()
        raw_job_description = st.text_area("Job Description")
        jd_url = st.text_input("Job URL")
        location = st.text_input("Location")
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Save Application")
    if submitted:
        if len(company) == 0 or len(role) == 0:
            st.error("Company and Role are required.")
        else:
            try:
                application_id = create_application(
                    company = company,
                    role = role,
                    raw_job_description= raw_job_description,
                    jd_url=jd_url,
                    location=location,
                    notes=notes)
                st.success("Application saved successfully! ID: {}".format(application_id))
            except sqlite3.Error as error:
                st.error(f"Failed to save application with error {error}")
else:
    st.write(placeholders[section])
