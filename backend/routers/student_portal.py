"""Student Portal Endpoints.

Handles comprehensive student profile management (personal, college, and parent details),
browsing enrolled course curriculum sessions, self-service attendance claims
(PRESENT requires admin approval; ABSENT is directly logged), and attendance history.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from backend.database import get_db
from backend.models.academic_models import (
    StudentProfileResponse,
    StudentProfileUpdate,
    StudentDetailedProfileUpdate,
    StudentAttendanceAction,
    AttendanceSubmit,
    StudentAttendanceRecord,
    EnrolledCourseResponse,
    CourseSessionItem,
    CourseInfo,
)

router = APIRouter(prefix="/api/student", tags=["Student Portal"])


# ==========================================
# 🎓 1. STUDENT PROFILE MANAGEMENT
# ==========================================

@router.get(
    "/profile/{student_id}",
    summary="Get Detailed Student Profile",
    response_description="Returns complete student profile with college, parent, and course data",
)
def get_student_profile(student_id: int):
    """Retrieve complete profile details for a given student ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.id, s.full_name, s.email, s.phone, s.department, s.semester, s.bio,
                   s.college_name, s.usn, s.degree, s.branch, s.graduation_year,
                   s.parent_name, s.parent_phone, s.parent_email, s.parent_relation,
                   s.course_id, c.code AS course_code, c.title AS course_title,
                   s.email_verified, s.phone_verified, s.approval_status, s.created_at
            FROM students s
            LEFT JOIN courses c ON s.course_id = c.id
            WHERE s.id = ?;
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
    summary="Update Detailed Student Profile",
    response_description="Updates personal, college, and parent details",
)
def update_detailed_profile(student_id: int, payload: StudentDetailedProfileUpdate):
    """Update student profile with comprehensive academic, college, and parent details.

    Sensitive contact verification flags (email_verified, phone_verified) and
    primary login identifiers remain immutable via this endpoint.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE students SET
                full_name = ?,
                department = ?,
                semester = ?,
                bio = ?,
                college_name = ?,
                usn = ?,
                degree = ?,
                branch = ?,
                graduation_year = ?,
                parent_name = ?,
                parent_phone = ?,
                parent_email = ?,
                parent_relation = ?
            WHERE id = ?;
            """,
            (
                payload.full_name.strip(),
                payload.department.strip(),
                payload.semester,
                payload.bio.strip() if payload.bio else "",
                payload.college_name.strip(),
                payload.usn.strip(),
                payload.degree.strip(),
                payload.branch.strip(),
                payload.graduation_year,
                payload.parent_name.strip(),
                payload.parent_phone.strip(),
                str(payload.parent_email).strip().lower() if payload.parent_email else "",
                payload.parent_relation.strip(),
                student_id,
            ),
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student record with ID {student_id} was not found.",
            )

    return {"status": "success", "message": "Profile, college, and parent details updated successfully."}


# ==========================================
# 📚 2. ENROLLED COURSE & SESSIONS
# ==========================================

@router.get(
    "/enrolled-course/{student_id}",
    summary="Get Enrolled Course and Curriculum Sessions",
    response_description="Returns enrolled course details and associated session schedule",
)
def get_enrolled_course_and_sessions(student_id: int):
    """Fetch the student's enrolled course and only curriculum sessions linked to that course."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Retrieve student course linkage
        cursor.execute(
            """
            SELECT s.course_id, c.code, c.title, c.description
            FROM students s
            JOIN courses c ON s.course_id = c.id
            WHERE s.id = ?;
            """,
            (student_id,),
        )
        course_row = cursor.fetchone()
        if not course_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student #{student_id} is not currently enrolled in a valid course.",
            )

        # Retrieve all sessions for this specific course alongside student attendance status
        cursor.execute(
            """
            SELECT sess.id AS session_id,
                   sess.topic,
                   sess.session_date,
                   sess.timing,
                   sess.mode,
                   sess.meeting_link,
                   sess.description,
                   COALESCE(att.status, 'NOT_SUBMITTED') AS attendance_status,
                   COALESCE(att.remarks, '') AS remarks
            FROM sessions sess
            LEFT JOIN attendance att ON sess.id = att.session_id AND att.student_id = ?
            WHERE sess.course_id = ?
            ORDER BY sess.session_date ASC, sess.id ASC;
            """,
            (student_id, course_row["course_id"]),
        )
        sessions = [dict(r) for r in cursor.fetchall()]

    return {
        "course": dict(course_row),
        "sessions": sessions,
    }


@router.get(
    "/sessions",
    summary="List All Published Sessions",
    response_description="List of all published academic curriculum sessions across courses",
)
def list_available_sessions():
    """Retrieve all scheduled academic curriculum sessions ordered chronologically."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, course_id, topic, session_date, timing, mode, meeting_link, description, created_at
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
            SELECT id, course_id, topic, session_date, timing, mode, meeting_link, description, created_at
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


# ==========================================
# 📝 3. ATTENDANCE SUBMISSION (PRESENT / ABSENT)
# ==========================================

@router.post(
    "/attendance/mark",
    summary="Submit Present or Absent Attendance Claim",
    status_code=status.HTTP_200_OK,
)
def mark_session_attendance(payload: StudentAttendanceAction):
    """Submit attendance claim for a curriculum session.

    - Claiming 'PRESENT': Marked as 'SUBMITTED' (pending admin/instructor approval).
    - Claiming 'ABSENT': Directly marked as 'ABSENT'.
    - Locked if instructor has already approved as 'PRESENT'.
    - Account must be 'APPROVED' by admin prior to marking attendance.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Validate student existence and onboarding approval state
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
                detail=f"Attendance locked. Onboarding status is '{student['approval_status']}'. Must be 'APPROVED'.",
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

        if existing_att and existing_att["status"] == "PRESENT":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attendance already finalized and approved as 'PRESENT' by the instructor.",
            )

        # 4. Map workflow: PRESENT -> SUBMITTED (pending review), ABSENT -> ABSENT
        assigned_status = "SUBMITTED" if payload.claim == "PRESENT" else "ABSENT"
        remark = (
            "Student claimed PRESENT (Pending Admin Approval)"
            if payload.claim == "PRESENT"
            else "Self-reported ABSENT"
        )

        cursor.execute(
            """
            INSERT INTO attendance (session_id, student_id, status, remarks)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id, student_id) DO UPDATE SET
                status = excluded.status,
                remarks = excluded.remarks,
                submitted_at = CURRENT_TIMESTAMP;
            """,
            (payload.session_id, payload.student_id, assigned_status, remark),
        )

    return {
        "status": "success",
        "attendance_status": assigned_status,
        "message": (
            "Claimed PRESENT. Pending Admin Approval."
            if payload.claim == "PRESENT"
            else "Marked as ABSENT."
        ),
        "student_id": payload.student_id,
        "session_id": payload.session_id,
    }


@router.post(
    "/attendance/submit",
    summary="Legacy Self-Service Attendance Submission",
    status_code=status.HTTP_200_OK,
)
def submit_session_attendance(payload: AttendanceSubmit):
    """Legacy endpoint: sets attendance to 'SUBMITTED' pending admin review."""
    return mark_session_attendance(
        StudentAttendanceAction(
            student_id=payload.student_id,
            session_id=payload.session_id,
            claim="PRESENT",
        )
    )


@router.get(
    "/attendance/history/{student_id}",
    summary="Get Student Attendance History",
    response_model=List[StudentAttendanceRecord],
)
def get_student_attendance_history(student_id: int):
    """Fetch complete academic curriculum sessions and personal verification statuses."""
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
