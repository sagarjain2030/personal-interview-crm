import streamlit as st

from db import create_application,get_all_applications, get_application_by_id,update_application_status
from db import update_application_priority
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

def record_data_dict(record_data):
    record_dict = dict()
    for re in record_data:
        record_dict[re[0]] = re[1] + " - " + re[2]
    return record_dict

application_status_dict = {
    0 : "Applied",
    1: "Interviewing",
    2: "Application Rejected",
    3: "Application Withdrawn",
    4: "Offer Received",
    5: "Offer Accepted",
    6 : "Offer Declined"
}

application_priority_dict = {
    1 : "Low",
    2: "Medium",
    3: "High",
}

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
    st.header("Saved Applications")
    record_data = get_all_applications()
    if record_data:
        columns = list(zip(*record_data))
        column_names = ["id", "Company",  "Role", "Status", "Created_at"]
        data = dict(zip(column_names,columns))
        st.dataframe(data)
        application_form_options = record_data_dict(record_data)
        selected_application = st.selectbox("Select Application", application_form_options.keys(),
                                            format_func= application_form_options.get)
        result = get_application_by_id(selected_application)
        if result:
            st.subheader(result[1])
            st.write(f"Role : {result[2]}")
            if result[3]:
                st.subheader("Job Description")
                st.write(result[3])
            if result[4]:
                st.subheader("Job URL")
                st.write(result[4])
            if result[5]:
                st.write(f"Location : {result[5]}")
            if result[6]:
                st.subheader("Notes")
                st.write(result[6])
            if result[7]:
                st.write(f"Created At : {result[7]}")
        selected_status = st.selectbox("Select Status", application_status_dict.keys(),
                                       format_func= application_status_dict.get,index=result[9])
        selected_priority = st.selectbox("Select Priority", application_priority_dict.keys(),
                                       format_func= application_priority_dict.get, index=result[11]-1)
        if st.button("Save Changes"):
            try:
                if selected_status != result[9]:
                    update_application_status(selected_application, selected_status)
                if selected_priority != result[11]:
                    update_application_priority(selected_application, selected_priority)
                st.success("Application Changes Saved successfully! ID: {}".format(selected_application))
            except sqlite3.Error as error:
                st.error(f"Failed to save application with error {error}")
    else :
        st.info("No saved applications yet.")
else:
    st.write(placeholders[section])


