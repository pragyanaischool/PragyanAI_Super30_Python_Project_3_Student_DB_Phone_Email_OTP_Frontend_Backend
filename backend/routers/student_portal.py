"""Student Portal Endpoints.

Handles student profile management, browsing scheduled curriculum sessions,
session detail retrieval, self-service attendance submission, and personal attendance history.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from backend.database import get_db
from backend.models.academic_models import (
    StudentProfileUpdate,
    AttendanceSubmit,
    StudentAttendanceRecord,
    SessionCreate,
)

router = APIRouter(prefix="/api/student", tags=["Student Portal"])


@router.get(
    "/profile/{student_id}",
    summary="Get Student Profile",
    response_description="Returns student profile details",
)
def get_student_profile(student_id: int):
    """Retrieve full profile details for a given student ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, full_name, email, phone, department, semester, bio, 
                   email_verified, phone_verified, approval_status, created_at
            FROM students 
            WHERE id = ?;
            """,
            (student_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student record with ID {student_id} was not found.",
            )
        return dict(row)


@router.put(
    "/profile/{student_id}",
    summary="Update Student Profile",
    response_description="Updates editable profile attributes",
)
def update_student_profile(student_id: int, payload: StudentProfileUpdate):
    """Update editable student details (full name, department, bio).

    Sensitive verification flags and contact identifiers (email, phone)
    remain immutable via this endpoint to preserve authentication integrity.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE students 
            SET full_name = ?, department = ?, bio = ?
            WHERE id = ?;
            """,
            (
                payload.full_name.strip(),
                payload.department.strip(),
                payload.bio.strip() if payload.bio else "",
                student_id,
            ),
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student record with ID {student_id} was not found.",
            )

    return {"status": "success", "message": "Profile updated successfully."}


@router.get(
    "/sessions",
    summary="List Scheduled Sessions",
    response_description="List of all published academic and training sessions",
)
def list_available_sessions():
    """Retrieve all scheduled academic sessions ordered chronologically."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, topic, session_date, timing, mode, meeting_link, description, created_at
            FROM sessions 
            ORDER BY session_date ASC, id ASC;
            """
        )
        return [dict(row) for row in cursor.fetchall()]


@router.get(
    "/sessions/{session_id}",
    summary="Get Session Detail",
    response_description="Detailed session attributes including link and timing",
)
def get_session_detail(session_id: int):
    """Retrieve specific session metadata: topic, date, timing, mode, and link."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, topic, session_date, timing, mode, meeting_link, description, created_at
            FROM sessions 
            WHERE id = ?;
            """,
            (session_id,),
        )
        session = cursor.fetchone()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session with ID {session_id} does not exist.",
            )
        return dict(session)


@router.post(
    "/attendance/submit",
    summary="Submit Session Attendance",
    status_code=status.HTTP_200_OK,
)
def submit_session_attendance(payload: AttendanceSubmit):
    """Self-submit attendance for an active session.

    Logs the student's submission as 'SUBMITTED' pending admin review.
    Guards against altering an attendance record that has already been verified
    by an instructor as PRESENT or ABSENT.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Validate student existence and onboarding approval
        cursor.execute(
            "SELECT approval_status FROM students WHERE id = ?;",
            (payload.student_id,),
        )
        student = cursor.fetchone()
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student #{payload.student_id} not found.",
            )
        if student["approval_status"] != "APPROVED":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Attendance recording locked. Account onboarding status is '{student['approval_status']}'. Must be 'APPROVED'.",
            )

        # 2. Validate session existence
        cursor.execute(
            "SELECT id FROM sessions WHERE id = ?;",
            (payload.session_id,),
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session #{payload.session_id} not found.",
            )

        # 3. Check existing attendance record status
        cursor.execute(
            "SELECT status FROM attendance WHERE session_id = ? AND student_id = ?;",
            (payload.session_id, payload.student_id),
        )
        existing_att = cursor.fetchone()

        if existing_att and existing_att["status"] in ("PRESENT", "ABSENT"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Attendance already finalized as '{existing_att['status']}' by the instructor.",
            )

        # 4. Upsert attendance record
        cursor.execute(
            """
            INSERT INTO attendance (session_id, student_id, status, remarks)
            VALUES (?, ?, 'SUBMITTED', 'Self-submitted via student dashboard')
            ON CONFLICT(session_id, student_id) DO UPDATE SET
                status = 'SUBMITTED',
                remarks = 'Self-submitted via student dashboard',
                submitted_at = CURRENT_TIMESTAMP;
            """,
            (payload.session_id, payload.student_id),
        )

    return {
        "status": "success",
        "message": "Attendance recorded successfully. Pending instructor approval.",
        "student_id": payload.student_id,
        "session_id": payload.session_id,
    }


@router.get(
    "/attendance/history/{student_id}",
    summary="Get Student Attendance History",
    response_model=List[StudentAttendanceRecord],
)
def get_student_attendance_history(student_id: int):
    """Fetch complete academic curriculum sessions and student verification statuses."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.topic, s.session_date, s.timing, s.mode,
                   COALESCE(a.status, 'NOT_SUBMITTED') AS status,
                   COALESCE(a.remarks, '') AS remarks,
                   a.submitted_at
            FROM sessions s
            LEFT JOIN attendance a ON s.id = a.session_id AND a.student_id = ?
            ORDER BY s.session_date DESC, s.id DESC;
            """,
            (student_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
