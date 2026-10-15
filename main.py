import streamlit as st

from db import create_application,get_all_applications, get_application_by_id,update_application_status, update_application_details
from db import update_application_priority, get_interviews_by_application_id
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

interview_round_type_dict = {
    0 : "Miscellaneous",
    1 : "Recruiter / HR Screening",
    2 : "Technical",
    3 : "Manager",
    4 : "Behavioral",
}

interview_result_type_dict = {
    0 : "Scheduled",
    1 : "Passed",
    2 : "Failed/Rejected",
    3 : "Cancelled",
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
            with st.form("Edit Application"):
                edit_company_details = st.text_input(label="Edit Company", value=result[1], key="EditCompany_" + result[0])
                edit_role_details = st.text_input(label="Edit Role",value=result[2], key="EditRole_"+ result[0])
                value_job_description = ""
                if result[3]:
                    value_job_description = result[3]
                edit_job_description_details = st.text_area(label="Edit Job Description", value=value_job_description, key="EditJobDescription_" + result[0])
                value_job_url = ""
                if result[4]:
                    value_job_url = result[4]
                edit_job_url_details = st.text_input(label="Edit Job url", value=value_job_url, key="EditJobURL_" + result[0])
                value_location = ""
                if result[5]:
                    value_location = result[5]
                edit_location_details = st.text_input(label="Edit Location", value=value_location, key="EditLocation_" + result[0])
                value_notes = ""
                if result[6]:
                    value_notes = result[6]
                edit_notes_details = st.text_area(label="Edit Job Notes", value=value_notes,key="EditJobnotes_" + result[0])
                if result[7]:
                    st.write(f"Created At : {result[7]}")
                preview_changes_button_value = st.form_submit_button("Preview Changes")
                save_edited_details_button_value = st.form_submit_button("Save Edit Changes")
            if preview_changes_button_value:
                edit_company_details = edit_company_details.strip()
                edit_role_details = edit_role_details.strip()
                if not edit_company_details or not edit_role_details:
                    st.error("Company and Role details are required.")
                else:
                    st.write(f"Company : {edit_company_details}")
                    st.write(f"Role : {edit_role_details}")
                    st.write(f"Job Description : {edit_job_description_details}")
                    st.write(f"Job URL : {edit_job_url_details}")
                    st.write(f"Location : {edit_location_details}")
                    st.write(f"Notes : {edit_notes_details}")
            if save_edited_details_button_value:
                edit_company_details = edit_company_details.strip()
                edit_role_details = edit_role_details.strip()
                if not edit_company_details or not edit_role_details:
                    st.error("Company and Role details are required.")
                else:
                    try:
                        update_application_details(selected_application, edit_company_details,
                                               edit_role_details,edit_job_description_details, edit_job_url_details,
                                               edit_location_details, edit_notes_details)
                        st.success(f"Application {selected_application} is updated successfully!")
                    except sqlite3.Error as error:
                        st.error(f"Failed to save edited application with error {error}")
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
elif section == "Interviews":
    application_list = get_all_applications()
    if application_list:
        application_selection_list = record_data_dict(application_list)
        selected_application = st.selectbox("Select Application", application_selection_list.keys(),
                                   format_func=application_selection_list.get)
        try:
            interviews_records = get_interviews_by_application_id(selected_application)
            if interviews_records:
                columns = list(zip(*interviews_records))
                column_names = ["id", "round_number", "round_type", "result"]
                data = dict(zip(column_names, columns))
                for v in data["round_type"]:
                    v = interview_round_type_dict[v]
                for v in data["result"]:
                    v = interview_result_type_dict[v]
                st.dataframe(data)
            else:
                st.info("No interviews recorded.")
        except sqlite3.Error as error:
            st.error(f"Failed to retrieve interviews with error {error}")
    else:
        st.info("No saved applications yet.")
else:
    st.write(placeholders[section])




