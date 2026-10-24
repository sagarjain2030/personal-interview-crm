import sqlite3

import streamlit as st

from db import (
    init_db,
    create_application,
    get_all_applications,
    get_application_by_id,
    update_application_status,
    update_application_details,
    update_application_priority,
    create_interview,
    get_interviews_by_application_id,
    create_interview_question,
    get_questions_by_interview_id,
)

APPLICATION_STATUS_LABELS = {
    0: "Applied",
    1: "Interviewing",
    2: "Application Rejected",
    3: "Application Withdrawn",
    4: "Offer Received",
    5: "Offer Accepted",
    6: "Offer Declined",
}

APPLICATION_PRIORITY_LABELS = {
    1: "Low",
    2: "Medium",
    3: "High",
}

INTERVIEW_ROUND_TYPE_LABELS = {
    0: "Miscellaneous",
    1: "Recruiter / HR Screening",
    2: "Technical Interview",
    3: "Hiring Manager Interview",
    4: "Behavioral / Culture Fit",
}

INTERVIEW_RESULT_LABELS = {
    0: "Scheduled",
    1: "Passed",
    2: "Failed / Rejected",
    3: "Cancelled",
}

PLACEHOLDERS = {
    "Insights": "Interview insights will appear here in a later step.",
}


def unique_labels(labels):
    """Append a short ID suffix to duplicate labels so they stay distinguishable in a selectbox."""
    label_values = list(labels.values())
    return {
        record_id: f"{label} ({record_id[:8]})" if label_values.count(label) > 1 else label
        for record_id, label in labels.items()
    }


def application_labels(applications):
    """Map each application UUID to a readable 'Company - Role' label."""
    return unique_labels({app[0]: f"{app[1]} - {app[2]}" for app in applications})


def interview_labels(interviews):
    """Map each interview UUID to a readable 'Round N — Round Type' label."""
    return unique_labels({
        interview[0]: f"Round {interview[1]} — {INTERVIEW_ROUND_TYPE_LABELS[interview[2]]}"
        for interview in interviews
    })


def load_applications():
    """Return all applications, or None after showing an error if the query fails."""
    try:
        return get_all_applications()
    except sqlite3.Error as error:
        st.error(f"Failed to load applications with error {error}")
        return None


def render_jobs_page():
    with st.form("application_form"):
        company = st.text_input("Company").strip()
        role = st.text_input("Role").strip()
        raw_job_description = st.text_area("Job Description")
        jd_url = st.text_input("Job URL")
        location = st.text_input("Location")
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Save Application")
    if submitted:
        if not company or not role:
            st.error("Company and Role are required.")
        else:
            try:
                application_id = create_application(
                    company=company,
                    role=role,
                    raw_job_description=raw_job_description,
                    jd_url=jd_url,
                    location=location,
                    notes=notes)
                st.success(f"Application saved successfully! ID: {application_id}")
            except sqlite3.Error as error:
                st.error(f"Failed to save application with error {error}")

    st.header("Saved Applications")
    applications = load_applications()
    if applications is None:
        return
    if not applications:
        st.info("No saved applications yet.")
        return

    column_names = ["id", "Company", "Role", "Status", "Created_at"]
    st.dataframe(dict(zip(column_names, zip(*applications))))

    labels = application_labels(applications)
    selected_application = st.selectbox("Select Application", labels.keys(), format_func=labels.get)
    result = get_application_by_id(selected_application)
    if not result:
        st.error("The selected application could not be loaded.")
        return

    with st.form("Edit Application"):
        edit_company_details = st.text_input(label="Edit Company", value=result[1], key="EditCompany_" + result[0])
        edit_role_details = st.text_input(label="Edit Role", value=result[2], key="EditRole_" + result[0])
        edit_job_description_details = st.text_area(label="Edit Job Description", value=result[3] or "",
                                                    key="EditJobDescription_" + result[0])
        edit_job_url_details = st.text_input(label="Edit Job url", value=result[4] or "", key="EditJobURL_" + result[0])
        edit_location_details = st.text_input(label="Edit Location", value=result[5] or "",
                                              key="EditLocation_" + result[0])
        edit_notes_details = st.text_area(label="Edit Job Notes", value=result[6] or "", key="EditJobnotes_" + result[0])
        if result[7]:
            st.write(f"Created At : {result[7]}")
        preview_changes_button_value = st.form_submit_button("Preview Changes")
        save_edited_details_button_value = st.form_submit_button("Save Edit Changes")

    if preview_changes_button_value or save_edited_details_button_value:
        edit_company_details = edit_company_details.strip()
        edit_role_details = edit_role_details.strip()
        if not edit_company_details or not edit_role_details:
            st.error("Company and Role details are required.")
        elif preview_changes_button_value:
            st.write(f"Company : {edit_company_details}")
            st.write(f"Role : {edit_role_details}")
            st.write(f"Job Description : {edit_job_description_details}")
            st.write(f"Job URL : {edit_job_url_details}")
            st.write(f"Location : {edit_location_details}")
            st.write(f"Notes : {edit_notes_details}")
        else:
            try:
                update_application_details(selected_application, edit_company_details,
                                           edit_role_details, edit_job_description_details, edit_job_url_details,
                                           edit_location_details, edit_notes_details)
                st.success(f"Application {selected_application} is updated successfully!")
            except sqlite3.Error as error:
                st.error(f"Failed to save edited application with error {error}")

    selected_status = st.selectbox("Select Status", APPLICATION_STATUS_LABELS.keys(),
                                   format_func=APPLICATION_STATUS_LABELS.get, index=result[9])
    selected_priority = st.selectbox("Select Priority", APPLICATION_PRIORITY_LABELS.keys(),
                                     format_func=APPLICATION_PRIORITY_LABELS.get, index=result[11] - 1)
    if st.button("Save Changes"):
        try:
            if selected_status != result[9]:
                update_application_status(selected_application, selected_status)
            if selected_priority != result[11]:
                update_application_priority(selected_application, selected_priority)
            st.success(f"Application Changes Saved successfully! ID: {selected_application}")
        except sqlite3.Error as error:
            st.error(f"Failed to save application with error {error}")


def render_interviews_page():
    applications = load_applications()
    if applications is None:
        return
    if not applications:
        st.info("No saved applications yet. Add one on the Jobs page first.")
        return

    labels = application_labels(applications)
    selected_application = st.selectbox("Select Application", labels.keys(), format_func=labels.get)

    # Handle the form before loading the list so a newly saved round appears immediately.
    st.subheader("Add Interview Round")
    with st.form("interview_form", clear_on_submit=True):
        round_number = st.number_input("Round Number", min_value=1, value=1, step=1)
        round_type = st.selectbox("Round Type", INTERVIEW_ROUND_TYPE_LABELS.keys(),
                                  format_func=INTERVIEW_ROUND_TYPE_LABELS.get)
        submitted = st.form_submit_button("Save Interview")
    if submitted:
        if round_number is None or int(round_number) < 1:
            st.error("Round number must be a whole number of 1 or more.")
        else:
            try:
                create_interview(selected_application, int(round_number), round_type)
                st.success(f"Round {int(round_number)} ({INTERVIEW_ROUND_TYPE_LABELS[round_type]}) "
                           f"saved for {labels[selected_application]}.")
            except sqlite3.Error as error:
                st.error(f"Failed to save interview with error {error}")

    st.subheader("Interview Rounds")
    try:
        interviews = get_interviews_by_application_id(selected_application)
    except sqlite3.Error as error:
        st.error(f"Failed to retrieve interviews with error {error}")
        return
    if not interviews:
        st.info("No interviews recorded for this application yet.")
        return

    rows = [
        {
            "Interview ID": interview_id,
            "Round Number": number,
            "Round Type": INTERVIEW_ROUND_TYPE_LABELS[type_value],
            "Result": INTERVIEW_RESULT_LABELS[result_value],
        }
        for interview_id, number, type_value, result_value in interviews
    ]
    st.dataframe(rows, hide_index=True)


def render_questions_page():
    applications = load_applications()
    if applications is None:
        return
    if not applications:
        st.info("No saved applications yet. Add one on the Jobs page first.")
        return

    labels = application_labels(applications)
    selected_application = st.selectbox("Select Application", labels.keys(), format_func=labels.get)

    try:
        interviews = get_interviews_by_application_id(selected_application)
    except sqlite3.Error as error:
        st.error(f"Failed to retrieve interviews with error {error}")
        return
    if not interviews:
        st.info("No interviews recorded for this application yet. Add one on the Interviews page first.")
        return

    round_labels = interview_labels(interviews)
    selected_interview = st.selectbox("Select Interview Round", round_labels.keys(), format_func=round_labels.get)

    # Handle the form before loading the list so a newly saved question appears immediately.
    st.subheader("Add Interview Question")
    with st.form("question_form", clear_on_submit=True):
        question = st.text_area("Interview Question")
        apparent_answer = st.text_area("My Answer / Apparent Answer (optional)")
        better_answer = st.text_area("Better Answer (optional)")
        submitted = st.form_submit_button("Save Question")
    if submitted:
        question = question.strip()
        if not question:
            st.error("Interview question is required.")
        else:
            try:
                create_interview_question(selected_interview, question,
                                          apparent_answer.strip() or None, better_answer.strip() or None)
                st.success(f"Question saved for {round_labels[selected_interview]}.")
            except sqlite3.Error as error:
                st.error(f"Failed to save question with error {error}")

    st.subheader("Saved Questions")
    try:
        questions = get_questions_by_interview_id(selected_interview)
    except sqlite3.Error as error:
        st.error(f"Failed to retrieve questions with error {error}")
        return
    if not questions:
        st.info("No questions recorded for this interview yet.")
        return

    # st.text shows the stored text as-is (multiline, no Markdown interpretation).
    for number, (_, question_text, apparent_text, better_text) in enumerate(questions, start=1):
        with st.container(border=True):
            st.markdown(f"**Question {number}**")
            st.text(question_text)
            st.markdown("**My Answer / Apparent Answer**")
            st.text(apparent_text or "Not recorded")
            st.markdown("**Better Answer**")
            st.text(better_text or "Not recorded")


st.set_page_config(page_title="Personal Interview CRM")
if not st.user.is_logged_in:
    _, login_col, _ = st.columns([1, 2, 1])
    with login_col.container(border=True):
        st.title("Personal Interview CRM")
        st.caption("Track job applications, interview rounds and questions in one place.")
        st.write("Sign in to continue.")
        if st.button("Sign in with Google", type="primary",
                     icon=":material/login:", width="stretch"):
            st.login()
    st.stop()
else:
    sub = st.user.get("sub")
    if (not st.secrets["access"]["allowed_google_sub"]
            or st.secrets["access"]["allowed_google_sub"] != sub):
        st.error("Access Denied")
        st.stop()
display_name = (
    st.user.get("name")
    or " ".join(filter(None, [st.user.get("given_name"), st.user.get("family_name")]))
    or st.user.get("email")
    or "Signed-in user"
)
title_col, user_col = st.columns([3, 1], vertical_alignment="bottom")
title_col.title("Personal Interview CRM")
user_col.markdown(f"**{display_name}**")
if user_col.button("Logout"):
    st.logout()

try:
    init_db()
except (sqlite3.Error, OSError) as error:
    st.error(f"Failed to initialize the database with error {error}")
    st.stop()

section = st.sidebar.radio(
    "Navigation",
    ["Jobs", "Interviews", "Questions", "Insights"],
)
st.header(section)

if section == "Jobs":
    render_jobs_page()
elif section == "Interviews":
    render_interviews_page()
elif section == "Questions":
    render_questions_page()
else:
    st.write(PLACEHOLDERS[section])
