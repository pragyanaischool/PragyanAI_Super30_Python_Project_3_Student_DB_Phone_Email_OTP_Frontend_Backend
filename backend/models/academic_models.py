"""Academic and Operational Pydantic Data Models.

Defines request/response schemas for Student Profile management,
Session publishing, Attendance logging, and Admin Approval workflows.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ==========================================
# 🏷️ ENUMERATIONS
# ==========================================

class ApprovalStatusEnum(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SessionModeEnum(str, Enum):
    ONLINE = "Online"
    OFFLINE = "Offline"
    HYBRID = "Hybrid"


class AttendanceStatusEnum(str, Enum):
    NOT_SUBMITTED = "NOT_SUBMITTED"
    SUBMITTED = "SUBMITTED"
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"


# ==========================================
# 🎓 STUDENT PORTAL SCHEMAS
# ==========================================

class StudentProfileUpdate(BaseModel):
    """Schema for student updating editable profile fields."""
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=120,
        description="Full name of the student",
        example="Sateesh Ambesange",
    )
    department: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Academic department or stream",
        example="Computer Science & Engineering",
    )
    bio: Optional[str] = Field(
        default="",
        max_length=500,
        description="Short student background or research interests",
        example="Focusing on Edge AI and Distributed Systems.",
    )


class AttendanceSubmit(BaseModel):
    """Schema for a student self-submitting attendance for a session."""
    student_id: int = Field(
        ...,
        gt=0,
        description="ID of the student claiming attendance",
        example=1,
    )
    session_id: int = Field(
        ...,
        gt=0,
        description="Target academic session ID",
        example=1,
    )


class StudentAttendanceRecord(BaseModel):
    """Schema for student's individual attendance history display."""
    topic: str
    session_date: str
    timing: str
    mode: str
    status: str
    remarks: Optional[str] = ""
    submitted_at: Optional[str] = None


# ==========================================
# 🛡️ ADMIN PORTAL SCHEMAS
# ==========================================

class StudentApprovalAction(BaseModel):
    """Schema for admin reviewing onboarding status of registered students."""
    status: ApprovalStatusEnum = Field(
        ...,
        description="Decision status: APPROVED, REJECTED, or PENDING",
        example=ApprovalStatusEnum.APPROVED,
    )


class SessionCreate(BaseModel):
    """Schema for creating a new lecture, workshop, or training session."""
    topic: str = Field(
        ...,
        min_length=3,
        max_length=200,
        description="Session title or lecture subject",
        example="Introduction to Agentic AI & LangGraph",
    )
    session_date: str = Field(
        ...,
        regex=r"^\d{4}-\d{2}-\d{2}$",
        description="Scheduled date in YYYY-MM-DD format",
        example="2026-10-01",
    )
    timing: str = Field(
        ...,
        min_length=3,
        max_length=60,
        description="Time slot of the session",
        example="10:00 AM - 12:00 PM",
    )
    mode: SessionModeEnum = Field(
        default=SessionModeEnum.ONLINE,
        description="Delivery mode: Online, Offline, or Hybrid",
        example=SessionModeEnum.ONLINE,
    )
    meeting_link: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Google Meet / Zoom link or classroom physical room location",
        example="https://meet.google.com/abc-prag-xyz",
    )
    description: Optional[str] = Field(
        default="",
        max_length=1000,
        description="Syllabus outline or prerequisites",
        example="Deep dive into multi-agent loops, state machines, and tool execution.",
    )


class AttendanceReview(BaseModel):
    """Schema for admin marking or verifying student attendance."""
    status: AttendanceStatusEnum = Field(
        ...,
        description="Verification mark: PRESENT or ABSENT",
        example=AttendanceStatusEnum.PRESENT,
    )
    remarks: Optional[str] = Field(
        default="",
        max_length=255,
        description="Instructor remarks or notes",
        example="Active participant during Q&A and submitted code exercises.",
    )


# ==========================================
# 📈 ANALYTICS & ROSTER SCHEMAS
# ==========================================

class SessionRosterItem(BaseModel):
    """Schema for individual student status in a session roster."""
    student_id: int
    full_name: str
    email: str
    department: str
    status: str
    remarks: Optional[str] = ""
    submitted_at: Optional[str] = None


class SessionAnalyticsItem(BaseModel):
    """Schema for aggregated attendance statistics per session."""
    session_id: int
    topic: str
    session_date: str
    mode: str
    present_count: int = 0
    absent_count: int = 0
    submitted_count: int = 0
    unaccounted_count: Optional[int] = 0
