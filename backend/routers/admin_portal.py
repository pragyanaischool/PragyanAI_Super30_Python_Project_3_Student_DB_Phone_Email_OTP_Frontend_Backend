"""Admin Portal Endpoints.

Handles student onboarding approvals/rejections, session creation,
session-wise roster inspection, attendance marking/reviews, and attendance analytics.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from backend.database import get_db
from backend.models.academic_models import (
    ApprovalStatusEnum,
    AttendanceReview,
    SessionAnalyticsItem,
    SessionCreate,
    SessionRosterItem,
    StudentApprovalAction,
)

router = APIRouter(prefix="/api/admin", tags=["Admin Portal"])


# ==========================================
# 👥 1. STUDENT ONBOARDING & APPROVALS
# ==========================================

@router.get(
    "/onboarding",
    summary="List Student Onboarding Applications",
    response_description="Returns list of registered students filtered by approval status",
)
def list_onboarding_students(
    status_filter: Optional[str] = Query(
        default="ALL",
        description="Filter by: ALL, PENDING, APPROVED, or REJECTED",
    )
):
    """Fetch students registered in the system with optional status filtering."""
    clean_filter = status_filter.strip().upper() if status_filter else "ALL"

    with get_db() as conn:
        cursor = conn.cursor()
        if clean_filter in ("PENDING", "APPROVED", "REJECTED"):
            cursor.execute(
                """
                SELECT id, full_name, email, phone, department, semester, bio,
                       email_verified, phone_verified, approval_status, created_at
                FROM students 
                WHERE approval_status = ?
                ORDER BY id DESC;
                """,
                (clean_filter,),
            )
        else:
            cursor.execute(
                """
                SELECT id, full_name, email, phone, department, semester, bio,
                       email_verified, phone_verified, approval_status, created_at
                FROM students 
                ORDER BY id DESC;
                """
            )
        students = [dict(row) for row in cursor.fetchall()]
        return students


@router.post(
    "/onboarding/{student_id}/action",
    summary="Update Student Onboarding Decision",
    status_code=status.HTTP_200_OK,
)
def set_student_approval_status(student_id: int, payload: StudentApprovalAction):
    """Set the onboarding approval state for a student (APPROVED, REJECTED, PENDING)."""
    decision = payload.status.value

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE students 
            SET approval_status = ? 
            WHERE id = ?;
            """,
            (decision, student_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student #{student_id} not found.",
            )

    return {
        "status": "success",
        "message": f"Student #{student_id} successfully marked as {decision}.",
        "student_id": student_id,
        "approval_status": decision,
    }


# ==========================================
# 📅 2. ACADEMIC SESSION MANAGEMENT
# ==========================================

@router.post(
    "/sessions",
    summary="Create & Publish Academic Session",
    status_code=status.HTTP_201_CREATED,
)
def create_session(payload: SessionCreate):
    """Create a new training, lecture, or workshop session."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sessions (topic, session_date, timing, mode, meeting_link, description)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                payload.topic.strip(),
                payload.session_date.strip(),
                payload.timing.strip(),
                payload.mode.value,
                payload.meeting_link.strip(),
                payload.description.strip() if payload.description else "",
            ),
        )
        new_session_id = cursor.lastrowid

    return {
        "status": "success",
        "message": "Academic session created and published successfully.",
        "session_id": new_session_id,
        "topic": payload.topic,
    }


# ==========================================
# 📝 3. ATTENDANCE ROSTER & REVIEWS
# ==========================================

@router.get(
    "/sessions/{session_id}/roster",
    summary="Get Session Attendance Roster",
    response_model=List[SessionRosterItem],
)
def get_session_attendance_roster(session_id: int):
    """Fetch attendance roster of all APPROVED students for a target session.

    Shows whether each student is PRESENT, ABSENT, SUBMITTED, or NOT_SUBMITTED.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Ensure session exists
        cursor.execute("SELECT id FROM sessions WHERE id = ?;", (session_id,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session #{session_id} not found.",
            )

        cursor.execute(
            """
            SELECT s.id as student_id, s.full_name, s.email, s.department,
                   COALESCE(a.status, 'NOT_SUBMITTED') as status,
                   COALESCE(a.remarks, '') as remarks,
                   a.submitted_at
            FROM students s
            LEFT JOIN attendance a ON s.id = a.student_id AND a.session_id = ?
            WHERE s.approval_status = 'APPROVED'
            ORDER BY s.id ASC;
            """,
            (session_id,),
        )
        roster = [dict(row) for row in cursor.fetchall()]
        return roster


@router.post(
    "/sessions/{session_id}/attendance/{student_id}",
    summary="Record or Review Student Attendance",
    status_code=status.HTTP_200_OK,
)
def review_student_attendance(
    session_id: int, student_id: int, payload: AttendanceReview
):
    """Approve or reject attendance for a student (marks as PRESENT or ABSENT with remarks)."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Validate student existence
        cursor.execute("SELECT id FROM students WHERE id = ?;", (student_id,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student #{student_id} not found.",
            )

        # Validate session existence
        cursor.execute("SELECT id FROM sessions WHERE id = ?;", (session_id,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session #{session_id} not found.",
            )

        # Upsert decision
        cursor.execute(
            """
            INSERT INTO attendance (session_id, student_id, status, remarks)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id, student_id) DO UPDATE SET
                status = excluded.status,
                remarks = excluded.remarks,
                submitted_at = CURRENT_TIMESTAMP;
            """,
            (
                session_id,
                student_id,
                payload.status.value,
                payload.remarks.strip() if payload.remarks else "",
            ),
        )

    return {
        "status": "success",
        "message": f"Student #{student_id} attendance updated to {payload.status.value}.",
        "session_id": session_id,
        "student_id": student_id,
        "status": payload.status.value,
    }


# ==========================================
# 📊 4. ATTENDANCE ANALYTICS
# ==========================================

@router.get(
    "/analytics/attendance",
    summary="Get Session-Wise Attendance Analytics",
    response_model=List[SessionAnalyticsItem],
)
def get_attendance_analytics():
    """Generates present, absent, pending review, and unaccounted metrics per session."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Total eligible (approved) students - safely read dict key instead of tuple index [0]
        cursor.execute(
            "SELECT COUNT(*) AS count FROM students WHERE approval_status = 'APPROVED';"
        )
        row = cursor.fetchone()
        total_eligible = row["count"] if row else 0

        # Group by all selected non-aggregate columns to strictly adhere to Postgres standard SQL
        cursor.execute(
            """
            SELECT 
                s.id as session_id,
                s.topic,
                s.session_date,
                s.mode,
                SUM(CASE WHEN a.status = 'PRESENT' THEN 1 ELSE 0 END) as present_count,
                SUM(CASE WHEN a.status = 'ABSENT' THEN 1 ELSE 0 END) as absent_count,
                SUM(CASE WHEN a.status = 'SUBMITTED' THEN 1 ELSE 0 END) as submitted_count
            FROM sessions s
            LEFT JOIN attendance a ON s.id = a.session_id
            GROUP BY s.id, s.topic, s.session_date, s.mode
            ORDER BY s.session_date DESC, s.id DESC;
            """
        )
        rows = cursor.fetchall()

        analytics_report = []
        for r in rows:
            p_cnt = r.get("present_count") or 0
            a_cnt = r.get("absent_count") or 0
            s_cnt = r.get("submitted_count") or 0
            accounted = p_cnt + a_cnt + s_cnt
            unaccounted = max(0, total_eligible - accounted)

            analytics_report.append(
                {
                    "session_id": r["session_id"],
                    "topic": r["topic"],
                    "session_date": r["session_date"],
                    "mode": r["mode"],
                    "present_count": p_cnt,
                    "absent_count": a_cnt,
                    "submitted_count": s_cnt,
                    "unaccounted_count": unaccounted,
                }
            )

        return analytics_report
