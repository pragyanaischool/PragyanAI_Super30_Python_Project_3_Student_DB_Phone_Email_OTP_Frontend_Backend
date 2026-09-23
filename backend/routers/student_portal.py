"""Student Portal Endpoints.

Handles student profile management, browsing scheduled training/curriculum sessions,
session detail retrieval, self-service attendance submission, and personal attendance history.
"""

from typing import List
from fastapi import APIRouter, HTTPException, status
from backend.database import get_db
from backend.models.academic_models import (
    StudentProfileUpdate,
    AttendanceSubmit,
    StudentAttendanceRecord,
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
            SELECT id, full_name, email, phone, department, bio, 
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

    return {"message": "Profile updated successfully."}


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
        sessions = [dict(row) for row in cursor.fetchall()]
        return sessions


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
    If already submitted, refreshes the submission timestamp.
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
                detail=f"Student onboarding status is '{student['approval_status']}'. Must be 'APPROVED' to submit attendance.",
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

        # 3. Upsert attendance record
        cursor.execute(
            """
            INSERT INTO attendance (session_id, student_id, status, remarks)
            VALUES (?, ?, 'SUBMITTED', 'Self-submitted via student dashboard')
            ON CONFLICT(session_id, student_id) DO UPDATE SET
            status = 'SUBMITTED',
            submitted_at = CURRENT_TIMESTAMP;
            """,
            (payload.session_id, payload.student_id),
        )

    return {
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
    """Fetch complete session attendance history and verification status for a student."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.topic, s.session_date, s.timing, s.mode,
                   a.status, COALESCE(a.remarks, '') as remarks,
                   a.submitted_at
            FROM attendance a
            JOIN sessions s ON a.session_id = s.id
            WHERE a.student_id = ?
            ORDER BY s.session_date DESC;
            """,
            (student_id,),
        )
        records = [dict(row) for row in cursor.fetchall()]
        return records
