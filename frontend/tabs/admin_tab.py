"""Admin Portal Tab Component for Gradio Frontend.

Provides:
1. Student Onboarding Approvals (Pending, Approved, Rejected filtering and actions).
2. Academic Session Creation and Publishing.
3. Session-Wise Attendance Roster Verification (Present/Absent marking with remarks).
4. Session Attendance Analytics and Performance Breakdown.
"""

from typing import List, Tuple
import gradio as gr
import pandas as pd
from backend.database import get_db
from frontend.tabs.student_tab import fetch_sessions_choices


def load_onboarding_roster(status_filter: str) -> pd.DataFrame:
    """Loads student records filtered by onboarding approval status."""
    columns = [
        "Student ID",
        "Full Name",
        "Email",
        "Phone",
        "Department",
        "Email Verified",
        "Phone Verified",
        "Approval Status",
    ]
    with get_db() as conn:
        cur = conn.cursor()
        if status_filter and status_filter.upper() != "ALL":
            cur.execute(
                """
                SELECT id, full_name, email, phone, department, 
                       email_verified, phone_verified, approval_status 
                FROM students 
                WHERE approval_status = ? 
                ORDER BY id DESC;
                """,
                (status_filter.upper(),),
            )
        else:
            cur.execute(
                """
                SELECT id, full_name, email, phone, department, 
                       email_verified, phone_verified, approval_status 
                FROM students 
                ORDER BY id DESC;
                """
            )
        rows = cur.fetchall()

    if not rows:
        return pd.DataFrame(columns=columns)

    data = [
        [
            r["id"],
            r["full_name"],
            r["email"],
            r["phone"],
            r["department"],
            "✅ Yes" if r["email_verified"] else "❌ No",
            "✅ Yes" if r["phone_verified"] else "❌ No",
            r["approval_status"],
        ]
        for r in rows
    ]
    return pd.DataFrame(data, columns=columns)


def process_onboarding_action(student_id: int, decision: str) -> str:
    """Updates student onboarding status to APPROVED or REJECTED."""
    if not student_id:
        return "❌ Please specify a valid Student ID."

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE students 
            SET approval_status = ? 
            WHERE id = ?;
            """,
            (decision.upper(), int(student_id)),
        )
        if cur.rowcount == 0:
            return f"❌ Student #{student_id} not found."

    icon = "✅" if decision.upper() == "APPROVED" else "🚫"
    return f"{icon} Student #{student_id} successfully marked as {decision.upper()}."


def publish_session(
    topic: str,
    session_date: str,
    timing: str,
    mode: str,
    meeting_link: str,
    description: str,
) -> str:
    """Creates and publishes a new academic session."""
    if not topic or not topic.strip():
        return "❌ Session Topic is required."
    if not session_date or not session_date.strip():
        return "❌ Session Date is required (YYYY-MM-DD)."
    if not meeting_link or not meeting_link.strip():
        return "❌ Meeting Link or Classroom Location is required."

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO sessions (topic, session_date, timing, mode, meeting_link, description)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                topic.strip(),
                session_date.strip(),
                timing.strip() if timing else "TBA",
                mode if mode else "Online",
                meeting_link.strip(),
                description.strip() if description else "",
            ),
        )
        new_id = cur.lastrowid

    return f"✅ Session #{new_id} ('{topic.strip()}') published successfully!"


def load_session_attendance_roster(selected_session: str) -> pd.DataFrame:
    """Loads roster of all approved students and their attendance status for a session."""
    columns = [
        "Student ID",
        "Student Name",
        "Email",
        "Department",
        "Attendance Status",
        "Admin Remarks",
        "Submission Time",
    ]
    if not selected_session:
        return pd.DataFrame(columns=columns)

    try:
        session_id = int(selected_session.split(":")[0])
    except (ValueError, IndexError):
        return pd.DataFrame(columns=columns)

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.id as student_id, s.full_name, s.email, s.department,
                   COALESCE(a.status, 'NOT_SUBMITTED') as status,
                   COALESCE(a.remarks, '') as remarks,
                   COALESCE(a.submitted_at, 'N/A') as submitted_at
            FROM students s
            LEFT JOIN attendance a ON s.id = a.student_id AND a.session_id = ?
            WHERE s.approval_status = 'APPROVED'
            ORDER BY s.id ASC;
            """,
            (session_id,),
        )
        rows = cur.fetchall()

    if not rows:
        return pd.DataFrame(columns=columns)

    data = [
        [
            r["student_id"],
            r["full_name"],
            r["email"],
            r["department"],
            r["status"],
            r["remarks"],
            r["submitted_at"],
        ]
        for r in rows
    ]
    return pd.DataFrame(data, columns=columns)


def update_student_attendance(
    selected_session: str, student_id: int, status_val: str, remarks: str
) -> str:
    """Records an administrative attendance decision (PRESENT or ABSENT) for a student."""
    if not selected_session:
        return "❌ Please select an active session first."
    if not student_id:
        return "❌ Please enter a valid Student ID."

    try:
        session_id = int(selected_session.split(":")[0])
    except (ValueError, IndexError):
        return "❌ Invalid session identifier."

    with get_db() as conn:
        cur = conn.cursor()

        # Validate that student exists and is approved
        cur.execute(
            "SELECT approval_status FROM students WHERE id = ?;",
            (int(student_id),),
        )
        st = cur.fetchone()
        if not st:
            return f"❌ Student #{student_id} does not exist."
        if st["approval_status"] != "APPROVED":
            return f"⚠️ Student #{student_id} is not APPROVED for onboarding."

        cur.execute(
            """
            INSERT INTO attendance (session_id, student_id, status, remarks)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id, student_id) DO UPDATE SET
            status = excluded.status,
            remarks = excluded.remarks;
            """,
            (
                session_id,
                int(student_id),
                status_val.upper(),
                remarks.strip() if remarks else f"Marked {status_val.upper()} by Admin",
            ),
        )

    icon = "✅" if status_val.upper() == "PRESENT" else "❌"
    return f"{icon} Student #{student_id} attendance marked as {status_val.upper()} for Session #{session_id}."


def load_attendance_analytics() -> pd.DataFrame:
    """Aggregates attendance metrics across all sessions."""
    columns = [
        "Session ID",
        "Session Topic",
        "Date",
        "Mode",
        "Present Count",
        "Absent Count",
        "Pending Review",
        "Total Eligible",
        "Attendance Rate (%)",
    ]
    with get_db() as conn:
        cur = conn.cursor()

        # Count total approved students eligible for sessions
        cur.execute("SELECT COUNT(*) FROM students WHERE approval_status = 'APPROVED';")
        total_eligible = cur.fetchone()[0] or 0

        cur.execute(
            """
            SELECT 
                s.id as session_id,
                s.topic,
                s.session_date,
                s.mode,
                SUM(CASE WHEN a.status = 'PRESENT' THEN 1 ELSE 0 END) as present_cnt,
                SUM(CASE WHEN a.status = 'ABSENT' THEN 1 ELSE 0 END) as absent_cnt,
                SUM(CASE WHEN a.status = 'SUBMITTED' THEN 1 ELSE 0 END) as pending_cnt
            FROM sessions s
            LEFT JOIN attendance a ON s.id = a.session_id
            GROUP BY s.id
            ORDER BY s.session_date DESC, s.id DESC;
            """
        )
        rows = cur.fetchall()

    if not rows:
        return pd.DataFrame(columns=columns)

    data = []
    for r in rows:
        present = r["present_cnt"] or 0
        absent = r["absent_cnt"] or 0
        pending = r["pending_cnt"] or 0
        rate = round((present / total_eligible * 100), 1) if total_eligible > 0 else 0.0

        data.append(
            [
                r["session_id"],
                r["topic"],
                r["session_date"],
                r["mode"],
                present,
                absent,
                pending,
                total_eligible,
                f"{rate}%",
            ]
        )

    return pd.DataFrame(data, columns=columns)


def create_admin_tab():
    """Renders the Admin Dashboard Tab inside a Gradio Blocks context."""
    with gr.Tab("🛡️ Admin Dashboard"):
        gr.Markdown("## 🛡️ Administrative Governance & Academic Oversight")

        # ---------------------------------------------------------
        # Section 1: Student Onboarding Approvals
        # ---------------------------------------------------------
        with gr.Group():
            gr.Markdown("### 1. Student Onboarding Approvals")
            with gr.Row():
                onboarding_filter = gr.Radio(
                    choices=["PENDING", "APPROVED", "REJECTED", "ALL"],
                    value="PENDING",
                    label="Filter Registered Students by Onboarding Status",
                    scale=3,
                )
                reload_roster_btn = gr.Button("🔄 Reload Applications", scale=1)

            onboarding_table = gr.DataFrame(
                headers=[
                    "Student ID",
                    "Full Name",
                    "Email",
                    "Phone",
                    "Department",
                    "Email Verified",
                    "Phone Verified",
                    "Approval Status",
                ],
                interactive=False,
                wrap=True,
            )

            with gr.Row():
                target_student_id = gr.Number(
                    label="Target Student ID for Action", precision=0, scale=2
                )
                approve_btn = gr.Button("✅ Approve Student", variant="primary", scale=1)
                reject_btn = gr.Button("🚫 Reject Student", variant="stop", scale=1)

            onboarding_action_msg = gr.Markdown()

        gr.Markdown("---")

        # ---------------------------------------------------------
        # Section 2: Session Creation & Publishing
        # ---------------------------------------------------------
        with gr.Group():
            gr.Markdown("### 2. Create & Publish Training Session")
            with gr.Row():
                new_topic = gr.Textbox(
                    label="Session Topic",
                    placeholder="e.g. LLM Inference Optimization on Linux Kernels",
                    scale=2,
                )
                new_date = gr.Textbox(
                    label="Date (YYYY-MM-DD)", placeholder="2026-10-15", scale=1
                )
                new_timing = gr.Textbox(
                    label="Time Window", placeholder="10:00 AM - 12:30 PM", scale=1
                )

            with gr.Row():
                new_mode = gr.Dropdown(
                    choices=["Online", "Offline", "Hybrid"],
                    value="Online",
                    label="Delivery Mode",
                    scale=1,
                )
                new_link = gr.Textbox(
                    label="Meeting Link / Classroom Venue",
                    placeholder="https://meet.google.com/... or Lab 402",
                    scale=3,
                )

            new_desc = gr.Textbox(
                label="Session Syllabus / Description",
                lines=2,
                placeholder="Key takeaways, required software setup, and hands-on modules...",
            )

            with gr.Row():
                publish_session_btn = gr.Button("➕ Publish Academic Session", variant="primary")

            publish_msg = gr.Markdown()

        gr.Markdown("---")

        # ---------------------------------------------------------
        # Section 3: Session Attendance Review & Roster
        # ---------------------------------------------------------
        with gr.Group():
            gr.Markdown("### 3. Session Roster & Attendance Verification")
            with gr.Row():
                admin_session_selector = gr.Dropdown(
                    label="Select Session to Review",
                    choices=fetch_sessions_choices(),
                    scale=3,
                )
                refresh_roster_btn = gr.Button("🔄 Load Session Roster", scale=1)

            session_roster_table = gr.DataFrame(
                headers=[
                    "Student ID",
                    "Student Name",
                    "Email",
                    "Department",
                    "Attendance Status",
                    "Admin Remarks",
                    "Submission Time",
                ],
                interactive=False,
                wrap=True,
            )

            with gr.Row():
                roster_student_id = gr.Number(
                    label="Target Student ID", precision=0, scale=1
                )
                mark_present_btn = gr.Button("✅ Mark Present", variant="primary", scale=1)
                mark_absent_btn = gr.Button("❌ Mark Absent", variant="stop", scale=1)
                review_remarks = gr.Textbox(
                    label="Instructor Notes / Remarks",
                    placeholder="e.g. Attended live demo and answered quiz",
                    scale=2,
                )

            attendance_review_msg = gr.Markdown()

        gr.Markdown("---")

        # ---------------------------------------------------------
        # Section 4: Attendance Analytics & Breakdown
        # ---------------------------------------------------------
        with gr.Group():
            with gr.Row():
                gr.Markdown("### 4. 📈 Session Attendance Analytics")
                reload_analytics_btn = gr.Button("🔄 Refresh Analytics", size="sm")

            analytics_table = gr.DataFrame(
                headers=[
                    "Session ID",
                    "Session Topic",
                    "Date",
                    "Mode",
                    "Present Count",
                    "Absent Count",
                    "Pending Review",
                    "Total Eligible",
                    "Attendance Rate (%)",
                ],
                interactive=False,
                wrap=True,
            )

        # ---------------------------------------------------------
        # Event Handlers
        # ---------------------------------------------------------
        reload_roster_btn.click(
            fn=load_onboarding_roster,
            inputs=onboarding_filter,
            outputs=onboarding_table,
        )

        onboarding_filter.change(
            fn=load_onboarding_roster,
            inputs=onboarding_filter,
            outputs=onboarding_table,
        )

        approve_btn.click(
            fn=lambda sid: process_onboarding_action(sid, "APPROVED"),
            inputs=target_student_id,
            outputs=onboarding_action_msg,
        ).then(
            fn=load_onboarding_roster,
            inputs=onboarding_filter,
            outputs=onboarding_table,
        ).then(
            fn=load_attendance_analytics,
            outputs=analytics_table,
        )

        reject_btn.click(
            fn=lambda sid: process_onboarding_action(sid, "REJECTED"),
            inputs=target_student_id,
            outputs=onboarding_action_msg,
        ).then(
            fn=load_onboarding_roster,
            inputs=onboarding_filter,
            outputs=onboarding_table,
        ).then(
            fn=load_attendance_analytics,
            outputs=analytics_table,
        )

        publish_session_btn.click(
            fn=publish_session,
            inputs=[new_topic, new_date, new_timing, new_mode, new_link, new_desc],
            outputs=publish_msg,
        ).then(
            fn=lambda: gr.update(choices=fetch_sessions_choices()),
            outputs=admin_session_selector,
        ).then(
            fn=load_attendance_analytics,
            outputs=analytics_table,
        )

        refresh_roster_btn.click(
            fn=load_session_attendance_roster,
            inputs=admin_session_selector,
            outputs=session_roster_table,
        )

        admin_session_selector.change(
            fn=load_session_attendance_roster,
            inputs=admin_session_selector,
            outputs=session_roster_table,
        )

        mark_present_btn.click(
            fn=lambda sess, sid, rem: update_student_attendance(sess, sid, "PRESENT", rem),
            inputs=[admin_session_selector, roster_student_id, review_remarks],
            outputs=attendance_review_msg,
        ).then(
            fn=load_session_attendance_roster,
            inputs=admin_session_selector,
            outputs=session_roster_table,
        ).then(
            fn=load_attendance_analytics,
            outputs=analytics_table,
        )

        mark_absent_btn.click(
            fn=lambda sess, sid, rem: update_student_attendance(sess, sid, "ABSENT", rem),
            inputs=[admin_session_selector, roster_student_id, review_remarks],
            outputs=attendance_review_msg,
        ).then(
            fn=load_session_attendance_roster,
            inputs=admin_session_selector,
            outputs=session_roster_table,
        ).then(
            fn=load_attendance_analytics,
            outputs=analytics_table,
        )

        reload_analytics_btn.click(
            fn=load_attendance_analytics,
            outputs=analytics_table,
        )
