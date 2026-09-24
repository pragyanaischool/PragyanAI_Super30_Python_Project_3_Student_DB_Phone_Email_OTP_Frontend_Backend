"""Academic and Operational Pydantic Data Models.

Defines request/response schemas for Student Authentication, Profile Management
(including College and Parent details), Course Enrollment, Session Rostering,
Attendance Claims, and Admin Governance Workflows.
Fully compatible with Pydantic v2 and Python 3.11 through 3.14+.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field, field_validator


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


class UserRoleEnum(str, Enum):
    STUDENT = "student"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


# ==========================================
# 🔐 AUTHENTICATION & ONBOARDING SCHEMAS
# ==========================================

class StudentSignupRequest(BaseModel):
    """Schema for new student registration with password credential creation."""
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=150,
        description="Full legal name of the student",
        examples=["Sateesh Ambesange"],
    )
    email: EmailStr = Field(
        ...,
        description="Official student institutional or personal email address",
        examples=["sateesh.ambesange@pragyanai.com"],
    )
    phone: str = Field(
        ...,
        pattern=r"^\+?[1-9]\d{7,14}$",
        description="International standard E.164 contact phone number",
        examples=["+919741007422"],
    )
    department: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Enrolled academic engineering or science department",
        examples=["Computer Science"],
    )
    semester: int = Field(
        default=1,
        ge=1,
        le=8,
        description="Current active semester (1-8)",
        examples=[8],
    )
    password: str = Field(
        ...,
        min_length=6,
        max_length=128,
        description="Account access password (minimum 6 characters)",
        examples=["SecurePass#2026"],
    )
    bio: Optional[str] = Field(
        default="",
        max_length=500,
        description="Research focus, tech interests, or project profile",
        examples=["AI Systems Architect focusing on Agentic AI, EDA, and Kernel Drivers."],
    )

    @field_validator("full_name", "department", mode="before")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v


class LoginRequest(BaseModel):
    """Unified login schema for identifier (email, phone, or username) and password."""
    identifier: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Student Email/Phone or Admin Username/Email",
        examples=["sateesh.ambesange@pragyanai.com"],
    )
    password: str = Field(
        ...,
        min_length=4,
        max_length=128,
        description="Plaintext password to authenticate against stored hash",
        examples=["admin123"],
    )

    @field_validator("identifier", mode="before")
    @classmethod
    def clean_identifier(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class AuthUserRecord(BaseModel):
    """Sanitized identity details returned upon successful authentication."""
    id: int
    full_name: Optional[str] = None
    username: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    department: Optional[str] = None
    semester: Optional[int] = 1
    role: str
    approval_status: Optional[str] = None
    phone_verified: Optional[bool] = False
    email_verified: Optional[bool] = False


class AuthResponse(BaseModel):
    """Standardized response returned to the client upon sign-in or signup."""
    status: str = "success"
    message: str
    role: UserRoleEnum
    user: AuthUserRecord


# ==========================================
# 🎓 STUDENT PROFILE & DETAILS SCHEMAS
# ==========================================

class StudentProfileResponse(BaseModel):
    """Complete student profile representation including college and parent records."""
    id: int
    full_name: str
    email: EmailStr
    phone: str
    department: str
    semester: int
    bio: Optional[str] = ""
    college_name: Optional[str] = ""
    usn: Optional[str] = ""
    degree: Optional[str] = "B.Tech"
    branch: Optional[str] = ""
    graduation_year: Optional[int] = 2027
    parent_name: Optional[str] = ""
    parent_phone: Optional[str] = ""
    parent_email: Optional[str] = ""
    parent_relation: Optional[str] = "Parent"
    course_id: Optional[int] = 1
    course_code: Optional[str] = None
    course_title: Optional[str] = None
    email_verified: bool
    phone_verified: bool
    approval_status: str
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class StudentProfileUpdate(BaseModel):
    """Minimal schema for updating basic editable non-credential fields."""
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=150,
        description="Full legal name of the student",
        examples=["Sateesh Ambesange"],
    )
    department: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Academic department or specialization stream",
        examples=["Computer Science"],
    )
    bio: Optional[str] = Field(
        default="",
        max_length=500,
        description="Research background or project interests",
        examples=["Focusing on Edge AI and Distributed Systems."],
    )

    @field_validator("full_name", "department", mode="before")
    @classmethod
    def clean_profile_fields(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class StudentDetailedProfileUpdate(BaseModel):
    """Full comprehensive profile update payload: Academic, College, Parent, and Contact details."""
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=150,
        description="Full legal name of the student",
        examples=["Sateesh Ambesange"],
    )
    department: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Department / School",
        examples=["Computer Science"],
    )
    semester: int = Field(
        default=1,
        ge=1,
        le=8,
        description="Current semester",
        examples=[8],
    )
    bio: Optional[str] = Field(
        default="",
        max_length=500,
        examples=["Focusing on Edge AI, Kernel drivers, and distributed inference."],
    )

    # College / Academic Details
    college_name: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="College or University institution name",
        examples=["National Institute of Technology Karnataka"],
    )
    usn: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="University Seat Number (USN) or Student Roll ID",
        examples=["1NT20CS001"],
    )
    degree: str = Field(
        default="B.Tech",
        max_length=50,
        description="Degree pursued (e.g. B.Tech, M.Tech, MCA)",
        examples=["B.Tech"],
    )
    branch: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Engineering branch or discipline",
        examples=["Computer Science & Engineering"],
    )
    graduation_year: int = Field(
        default=2027,
        ge=2020,
        le=2035,
        description="Expected or actual year of graduation",
        examples=[2027],
    )

    # Parent / Guardian Details
    parent_name: str = Field(
        ...,
        min_length=2,
        max_length=150,
        description="Parent or legal guardian name",
        examples=["Ramesh Ambesange"],
    )
    parent_phone: str = Field(
        ...,
        pattern=r"^\+?[1-9]\d{7,14}$",
        description="Parent or guardian contact phone number",
        examples=["+919876543210"],
    )
    parent_email: Optional[EmailStr] = Field(
        default=None,
        description="Parent contact email",
        examples=["parent.contact@gmail.com"],
    )
    parent_relation: str = Field(
        default="Parent",
        max_length=50,
        description="Relationship to student (Father, Mother, Guardian)",
        examples=["Father"],
    )

    @field_validator("full_name", "department", "college_name", "usn", "branch", "parent_name", mode="before")
    @classmethod
    def strip_required_strings(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


# ==========================================
# 📚 COURSES & SESSIONS SCHEMAS
# ==========================================

class CourseSessionItem(BaseModel):
    """Schema representing an academic session listed under an enrolled course."""
    session_id: int
    topic: str
    session_date: str
    timing: str
    mode: str
    meeting_link: str
    description: Optional[str] = ""
    attendance_status: str = "NOT_SUBMITTED"
    remarks: Optional[str] = ""


class CourseInfo(BaseModel):
    """Course metadata schema."""
    course_id: int
    code: str
    title: str
    description: Optional[str] = ""


class EnrolledCourseResponse(BaseModel):
    """Schema returning enrolled course metadata alongside all associated sessions."""
    course: CourseInfo
    sessions: List[CourseSessionItem]


class SessionCreate(BaseModel):
    """Schema for scheduling and publishing a curriculum session or workshop."""
    course_id: Optional[int] = Field(
        default=1,
        gt=0,
        description="Target course ID the session belongs to",
        examples=[1],
    )
    topic: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Session lecture topic or subject title",
        examples=["Agentic AI Architecture & Multi-Agent LangGraph Systems"],
    )
    session_date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Scheduled date formatted strictly as YYYY-MM-DD",
        examples=["2026-10-01"],
    )
    timing: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Lecture timing slot window",
        examples=["10:00 AM - 12:30 PM"],
    )
    mode: SessionModeEnum = Field(
        default=SessionModeEnum.ONLINE,
        description="Delivery mode: Online, Offline, or Hybrid",
        examples=[SessionModeEnum.ONLINE],
    )
    meeting_link: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Google Meet / Zoom URL or classroom physical room location",
        examples=["https://meet.google.com/abc-prag-xyz"],
    )
    description: Optional[str] = Field(
        default="",
        max_length=1000,
        description="Syllabus outline, lecture roadmap, or prerequisites",
        examples=["Deep dive into multi-agent loops, state machines, and tool execution."],
    )

    @field_validator("topic", "session_date", "timing", "meeting_link", mode="before")
    @classmethod
    def clean_session_fields(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class SessionResponse(BaseModel):
    """Schema for returning session metadata to the client."""
    id: int
    course_id: Optional[int] = 1
    topic: str
    session_date: str
    timing: str
    mode: str
    meeting_link: str
    description: Optional[str] = ""
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


# ==========================================
# 📝 ATTENDANCE WORKFLOW SCHEMAS
# ==========================================

class AttendanceSubmit(BaseModel):
    """Schema for legacy student self-service attendance submission."""
    student_id: int = Field(..., gt=0, examples=[1])
    session_id: int = Field(..., gt=0, examples=[1])


class StudentAttendanceAction(BaseModel):
    """Payload for student submitting Present or Absent claim."""
    student_id: int = Field(
        ...,
        gt=0,
        description="Database primary key ID of student",
        examples=[1],
    )
    session_id: int = Field(
        ...,
        gt=0,
        description="Database primary key ID of academic session",
        examples=[1],
    )
    claim: str = Field(
        ...,
        pattern=r"^(PRESENT|ABSENT)$",
        description="Self-reported claim: 'PRESENT' (sent for Admin approval) or 'ABSENT'",
        examples=["PRESENT"],
    )


class StudentAttendanceRecord(BaseModel):
    """Schema for individual student attendance history timeline."""
    topic: str
    session_date: str
    timing: str
    mode: str
    status: str
    remarks: Optional[str] = ""
    submitted_at: Optional[str] = None


class AttendanceReview(BaseModel):
    """Schema for administrator verifying and finalizing student attendance."""
    status: AttendanceStatusEnum = Field(
        ...,
        description="Verification mark: PRESENT or ABSENT",
        examples=[AttendanceStatusEnum.PRESENT],
    )
    remarks: Optional[str] = Field(
        default="",
        max_length=255,
        description="Instructor feedback comments or review notes",
        examples=["Active participant during live Q&A and code walkthrough."],
    )

    @field_validator("remarks", mode="before")
    @classmethod
    def clean_remarks(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else ""


# ==========================================
# 🛡️ ADMIN GOVERNANCE & ANALYTICS SCHEMAS
# ==========================================

class StudentApprovalAction(BaseModel):
    """Schema for administrator deciding onboarding approval state."""
    status: ApprovalStatusEnum = Field(
        ...,
        description="Decision outcome: APPROVED, REJECTED, or PENDING",
        examples=[ApprovalStatusEnum.APPROVED],
    )


class SessionRosterItem(BaseModel):
    """Schema representing a student row in an instructor's session grading roster."""
    student_id: int
    full_name: str
    email: EmailStr
    department: str
    status: str
    remarks: Optional[str] = ""
    submitted_at: Optional[str] = None


class SessionAnalyticsItem(BaseModel):
    """Schema for aggregated attendance statistics per curriculum session."""
    session_id: int
    topic: str
    session_date: str
    mode: str
    present_count: int = 0
    absent_count: int = 0
    submitted_count: int = 0
    unaccounted_count: Optional[int] = 0


class StandardMessageResponse(BaseModel):
    """Standard generic API response format for write actions."""
    status: str = "success"
    message: str
    data: Optional[Dict[str, Any]] = None
