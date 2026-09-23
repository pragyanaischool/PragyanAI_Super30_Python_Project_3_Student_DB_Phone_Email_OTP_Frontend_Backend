"""Student Portal Tab Component for Gradio Frontend.

Provides:
1. Student Profile inspection and editing (keeping contact/auth read-only).
2. Scheduled session selector with detailed metadata (Topic, Date, Timing, Mode, Link).
3. One-click attendance submission.
4. Historical attendance records table.
"""

from typing import List, Tuple
import gradio as gr
import pandas as pd
from backend.database import get_db


def fetch_sessions_choices() -> List[str]:
    """Retrieves all sessions formatted for Gradio dropdown choices."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, topic, session_date 
            FROM sessions 
            ORDER BY session_date ASC, id ASC;
            """
        )
        rows = cur.fetchall()
        if not rows:
            return []
        return [f"{r['id']}: {r['topic']} ({r['session_date']})" for r in rows]


def load_profile(student_id: int) -> Tuple[str, str, str, str, str, str]:
    """Loads student record by ID."""
    if not student_id:
        return "", "", "", "", "", "❌ Please enter a valid Student ID."

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT full_name, email, phone, department, bio, approval_status 
            FROM students 
            WHERE id = ?;
            """,
            (int(student_id),),
        )
        row = cur.fetchone()
        if not row:
            return "", "", "", "", "", f"❌ Student #{student_id} not found."

        return (
            row["full_name"] or "",
            row["email"] or "",
            row["phone"] or "",
            row["department"] or "",
            row["bio"] or "",
            row["approval_status"] or "PENDING",
        )


def update_profile(
    student_id: int, full_name: str, department: str, bio: str
) -> str:
    """Updates editable student profile fields."""
    if not student_id:
        return "❌ Student ID is required."
    if not full_name or not full_name.strip():
        return "❌ Full Name cannot be empty."

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE students 
            SET full_name = ?, department = ?, bio = ? 
            WHERE id = ?;
            """,
            (
                full_name.strip(),
                department.strip() if department else "",
                bio.strip() if bio else "",
                int(student_id),
            ),
        )
        if cur.rowcount == 0:
            return f"❌ Student #{student_id} not found."

    return "✅ Profile updated successfully!"


def get_session_info(selected_choice: str) -> Tuple[str, str, str, str, str, str]:
    """Fetches details for a selected session choice."""
    if not selected_choice:
        return "", "", "", "", "", ""

    try:
        session_id = int(selected_choice.split(":")[0])
    except (ValueError, IndexError):
        return "", "", "", "", "", ""

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT topic, session_date, timing, mode, meeting_link, description 
            FROM sessions 
            WHERE id = ?;
            """,
            (session_id,),
        )
        row = cur.fetchone()
        if not row:
            return "", "", "", "", "", ""

        return (
            row["topic"] or "",
            row["session_date"] or "",
            row["timing"] or "",
            row["mode"] or "Online",
            row["meeting_link"] or "",
            row["description"] or "",
        )


def submit_attendance(student_id: int, selected_choice: str) -> str:
    """Submits attendance record for instructor verification."""
    if not student_id:
        return "❌ Student ID is required to submit attendance."
    if not selected_choice:
        return "❌ Please select a session from the dropdown first."

    try:
        session_id = int(selected_choice.split(":")[0])
    except (ValueError, IndexError):
        return "❌ Invalid session selection."

    with get_db() as conn:
        cur = conn.cursor()

        # Validate student approval status
        cur.execute(
            "SELECT approval_status FROM students WHERE id = ?;",
            (int(student_id),),
        )
        student = cur.fetchone()
        if not student:
            return f"❌ Student #{student_id} does not exist."
        if student["approval_status"] != "APPROVED":
            return f"⚠️ Cannot submit attendance: Onboarding status is '{student['approval_status']}'. Must be APPROVED."

        # Upsert attendance record
        cur.execute(
            """
            INSERT INTO attendance (session_id, student_id, status, remarks)
            VALUES (?, ?, 'SUBMITTED', 'Submitted via Student Portal')
            ON CONFLICT(session_id, student_id) DO UPDATE SET
            status = 'SUBMITTED',
            submitted_at = CURRENT_TIMESTAMP;
            """,
            (session_id, int(student_id)),
        )

    return "✅ Attendance submitted successfully! Awaiting instructor review."


def get_student_attendance_history(student_id: int) -> pd.DataFrame:
    """Retrieves full attendance history for the given student."""
    columns = [
        "Session Topic",
        "Date",
        "Time",
        "Mode",
        "Status",
        "Instructor Remarks",
        "Submitted At",
    ]
    if not student_id:
        return pd.DataFrame(columns=columns)

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.topic, s.session_date, s.timing, s.mode,
                   a.status, COALESCE(a.remarks, '') as remarks,
                   a.submitted_at
            FROM attendance a
            JOIN sessions s ON a.session_id = s.id
            WHERE a.student_id = ?
            ORDER BY s.session_date DESC, s.id DESC;
            """,
            (int(student_id),),
        )
        records = cur.fetchall()

    if not records:
        return pd.DataFrame(columns=columns)

    data = [
        [
            r["topic"],
            r["session_date"],
            r["timing"],
            r["mode"],
            r["status"],
            r["remarks"],
            r["submitted_at"],
        ]
        for r in records
    ]
    return pd.DataFrame(data, columns=columns)


def create_student_tab():
    """Renders the Student Portal Tab inside a Gradio Blocks context."""
    with gr.Tab("🎓 Student Dashboard"):
        gr.Markdown("## 🎓 Student Profile & Academic Hub")

        # ---------------------------------------------------------
        # Section 1: Active Student Context & Profile Management
        # ---------------------------------------------------------
        with gr.Group():
            with gr.Row():
                student_id_input = gr.Number(
                    value=1,
                    label="Current Student ID (Session Context)",
                    precision=0,
                    scale=2,
                )
                load_profile_btn = gr.Button("🔄 Load Student Profile", scale=1)

            gr.Markdown("### 👤 Profile Details")
            with gr.Row():
                name_input = gr.Textbox(label="Full Name", placeholder="e.g. Sateesh Ambesange")
                dept_input = gr.Textbox(label="Department", placeholder="e.g. Computer Science")
            with gr.Row():
                email_display = gr.Textbox(label="Verified Email", interactive=False)
                phone_display = gr.Textbox(label="Verified Phone", interactive=False)
                status_display = gr.Textbox(label="Onboarding Approval Status", interactive=False)
            bio_input = gr.Textbox(
                label="Bio / Specialization",
                lines=2,
                placeholder="Briefly state your technical interests or academic focus...",
            )

            with gr.Row():
                save_profile_btn = gr.Button("💾 Save Profile Changes", variant="primary")
            profile_feedback = gr.Markdown()

        gr.Markdown("---")

        # ---------------------------------------------------------
        # Section 2: Session Browser & Attendance Action
        # ---------------------------------------------------------
        with gr.Group():
            gr.Markdown("### 📅 Browse Scheduled Sessions & Fill Attendance")
            with gr.Row():
                session_selector = gr.Dropdown(
                    label="Select Academic / Training Session",
                    choices=fetch_sessions_choices(),
                    scale=3,
                )
                refresh_sessions_btn = gr.Button("🔄 Refresh Sessions", scale=1)

            with gr.Row():
                sess_topic = gr.Textbox(label="Topic", interactive=False)
                sess_date = gr.Textbox(label="Date", interactive=False)
                sess_timing = gr.Textbox(label="Timing", interactive=False)
            with gr.Row():
                sess_mode = gr.Textbox(label="Delivery Mode", interactive=False)
                sess_link = gr.Textbox(label="Meeting Link / Classroom Venue", interactive=False)
            sess_desc = gr.Textbox(label="Session Overview / Syllabus", lines=2, interactive=False)

            with gr.Row():
                submit_att_btn = gr.Button("📝 Fill & Submit Attendance", variant="primary")
            att_feedback = gr.Markdown()

        gr.Markdown("---")

        # ---------------------------------------------------------
        # Section 3: Attendance History Table
        # ---------------------------------------------------------
        with gr.Group():
            with gr.Row():
                gr.Markdown("### 📊 My Attendance History & Statuses")
                refresh_history_btn = gr.Button("🔄 Refresh Attendance Table", size="sm")

            history_table = gr.DataFrame(
                headers=[
                    "Session Topic",
                    "Date",
                    "Time",
                    "Mode",
                    "Status",
                    "Instructor Remarks",
                    "Submitted At",
                ],
                interactive=False,
                wrap=True,
            )

        # ---------------------------------------------------------
        # Event Handlers
        # ---------------------------------------------------------
        load_profile_btn.click(
            fn=load_profile,
            inputs=student_id_input,
            outputs=[
                name_input,
                email_display,
                phone_display,
                dept_input,
                bio_input,
                status_display,
            ],
        ).then(
            fn=get_student_attendance_history,
            inputs=student_id_input,
            outputs=history_table,
        )

        save_profile_btn.click(
            fn=update_profile,
            inputs=[student_id_input, name_input, dept_input, bio_input],
            outputs=profile_feedback,
        )

        refresh_sessions_btn.click(
            fn=lambda: gr.update(choices=fetch_sessions_choices()),
            outputs=session_selector,
        )

        session_selector.change(
            fn=get_session_info,
            inputs=session_selector,
            outputs=[
                sess_topic,
                sess_date,
                sess_timing,
                sess_mode,
                sess_link,
                sess_desc,
            ],
        )

        submit_att_btn.click(
            fn=submit_attendance,
            inputs=[student_id_input, session_selector],
            outputs=att_feedback,
        ).then(
            fn=get_student_attendance_history,
            inputs=student_id_input,
            outputs=history_table,
        )

        refresh_history_btn.click(
            fn=get_student_attendance_history,
            inputs=student_id_input,
            outputs=history_table,
        )
