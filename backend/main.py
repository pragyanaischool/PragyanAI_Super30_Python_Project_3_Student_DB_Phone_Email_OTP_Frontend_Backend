import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

# Ensure project root is available on sys.path across all execution contexts
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from fastapi import FastAPI, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

try:
    from backend.config import settings
    from backend.database import init_db, get_db
    from backend.services.otp_service import OTPService
    from backend.services.twilio_service import TwilioService
    from backend.services.email_service import EmailService
    from backend.routers.student_portal import router as student_router
    from backend.routers.admin_portal import router as admin_router
except ImportError:
    from config import settings
    from database import init_db, get_db
    from services.otp_service import OTPService
    from services.twilio_service import TwilioService
    from services.email_service import EmailService
    from routers.student_portal import router as student_router
    from routers.admin_portal import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure database tables, sample data, and indexes exist on application startup."""
    init_db()
    yield


# Initialize FastAPI Application
app = FastAPI(
    title="Student DB & Academic Management Portal API",
    description="Backend API for student registration, verification, student self-service portal, and admin governance.",
    version="2.3.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------
# CORS Middleware Configuration
# ---------------------------------------------------------
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:7860",
    "http://127.0.0.1:7860",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Core Services
otp_service = OTPService(expiry_seconds=settings.OTP_EXPIRY_SECONDS)
twilio_service = TwilioService()
email_service = EmailService()


# ---------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------
class StudentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=20)
    department: str = Field(..., min_length=2, max_length=100)
    semester: int = Field(..., ge=1, le=8)


class VerifyOTPRequest(BaseModel):
    identifier: str = Field(..., description="Phone number or email address to verify")
    otp: str = Field(..., min_length=4, max_length=10)
    type: str = Field(..., pattern="^(phone|email)$", description="Type must be either 'phone' or 'email'")


class ResendOTPRequest(BaseModel):
    identifier: str = Field(..., description="Phone number or Email address to resend OTP to")


# ---------------------------------------------------------
# System & Debug Endpoints
# ---------------------------------------------------------
@app.get("/api/health", tags=["System"])
def health_check():
    """Health check endpoint for Render monitoring."""
    return {"status": "healthy", "service": "student-db-api"}


@app.get("/api/debug/recent-otp", tags=["Debug"])
def get_recent_otp(identifier: str = Query(..., description="Phone number or email address")):
    """Helper endpoint to inspect active OTP in case SMS/Email gateway drops it."""
    clean_id = identifier.strip()

    # Search across known store attribute names in OTPService
    store = None
    for attr in ["otp_store", "_store", "otps", "_otps", "cache", "_cache"]:
        if hasattr(otp_service, attr):
            store = getattr(otp_service, attr)
            break

    if store is None:
        raise HTTPException(status_code=500, detail="OTP store attribute not found on OTPService.")

    # Match identifier directly or lowercase (for emails)
    entry = store.get(clean_id) or store.get(clean_id.lower())

    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"No active OTP found for '{clean_id}' or code has expired."
        )

    # Safely extract code whether stored as tuple (code, expiry), dict, list, or primitive string
    if isinstance(entry, (tuple, list)):
        code_val = entry[0]
    elif isinstance(entry, dict):
        code_val = entry.get("otp") or entry.get("code") or list(entry.values())[0]
    else:
        code_val = str(entry)

    return {
        "identifier": clean_id,
        "active_otp": str(code_val)
    }


# ---------------------------------------------------------
# Registration & Verification Endpoints
# ---------------------------------------------------------
@app.post("/api/students/register", status_code=status.HTTP_201_CREATED, tags=["Students"])
def register_student(student: StudentCreate):
    """Register a new student and dispatch SMS and Email OTPs."""
    phone_clean = student.phone.strip()
    email_clean = student.email.strip().lower()

    with get_db() as conn:
        cursor = conn.cursor()

        # Check uniqueness for email or phone
        cursor.execute(
            "SELECT id FROM students WHERE email = ? OR phone = ?",
            (email_clean, phone_clean)
        )
        if cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A student with this email or phone number is already registered."
            )

        # Insert new record (sets approval_status to 'PENDING' by default)
        cursor.execute("""
            INSERT INTO students (full_name, email, phone, department, semester, approval_status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')
        """, (student.name.strip(), email_clean, phone_clean, student.department.strip(), student.semester))

    # Generate and record verification OTPs
    phone_otp = otp_service.generate_otp(phone_clean)
    email_otp = otp_service.generate_otp(email_clean)

    # Dispatch alerts via Twilio and Brevo
    sms_sent = twilio_service.send_sms(
        to_phone=phone_clean,
        message=f"Your verification code is: {phone_otp}. Valid for 5 minutes."
    )

    mail_sent = email_service.send_email(
        to_email=email_clean,
        subject="Student Portal Verification Code",
        content=f"Hello {student.name},\n\nYour portal OTP is: {email_otp}\n\nValid for 5 minutes."
    )

    return {
        "message": "Registration successful. OTPs dispatched to both phone and email.",
        "phone": phone_clean,
        "email": email_clean,
        "sms_dispatched": sms_sent,
        "email_dispatched": mail_sent
    }


@app.post("/api/students/verify-otp", tags=["Students"])
def verify_student_otp(payload: VerifyOTPRequest):
    """Verify submitted OTP and update student verification flags."""
    identifier = payload.identifier.strip()
    if payload.type == "email":
        identifier = identifier.lower()

    # Constant-time comparison validation
    is_valid = otp_service.verify_otp(identifier, payload.otp.strip())
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP."
        )

    target_col = "phone_verified" if payload.type == "phone" else "email_verified"
    id_col = "phone" if payload.type == "phone" else "email"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE students SET {target_col} = 1 WHERE {id_col} = ?",
            (identifier,)
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student record matching '{identifier}' was not found."
            )

    return {"message": f"{payload.type.capitalize()} verified successfully."}


@app.post("/api/students/resend-otp/phone", tags=["Students"])
def resend_phone_otp(payload: ResendOTPRequest):
    """Regenerates and resends OTP specifically to a student's phone number."""
    phone_clean = payload.identifier.strip()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name, phone_verified FROM students WHERE phone = ?", (phone_clean,))
        student = cursor.fetchone()

        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student with this phone number not found.")
        if student["phone_verified"] == 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This phone number is already verified.")

    phone_otp = otp_service.generate_otp(phone_clean)

    sms_sent = twilio_service.send_sms(
        to_phone=phone_clean,
        message=f"Your new verification code is: {phone_otp}. Valid for 5 minutes."
    )

    return {
        "status": "success",
        "message": f"New OTP sent to phone {phone_clean}",
        "channel": "phone",
        "sms_dispatched": sms_sent
    }


@app.post("/api/students/resend-otp/email", tags=["Students"])
def resend_email_otp(payload: ResendOTPRequest):
    """Regenerates and resends OTP specifically to a student's email address."""
    email_clean = payload.identifier.strip().lower()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name, email_verified FROM students WHERE email = ?", (email_clean,))
        student = cursor.fetchone()

        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student with this email address not found.")
        if student["email_verified"] == 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This email address is already verified.")

    email_otp = otp_service.generate_otp(email_clean)

    mail_sent = email_service.send_email(
        to_email=email_clean,
        subject="Student Portal Verification Code (Resend)",
        content=f"Hello {student['full_name']},\n\nYour new portal OTP is: {email_otp}\n\nValid for 5 minutes."
    )

    return {
        "status": "success",
        "message": f"New OTP sent to email {email_clean}",
        "channel": "email",
        "email_dispatched": mail_sent
    }


# ---------------------------------------------------------
# Analytics & Directory Endpoints
# ---------------------------------------------------------
@app.get("/api/analytics", tags=["Analytics"])
def get_analytics():
    """Retrieve operational KPIs, departmental counts, and verification rates."""
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) AS count FROM students")
        row = cur.fetchone()
        total_students = row["count"] if row else 0

        cur.execute("SELECT COUNT(*) AS count FROM students WHERE phone_verified = 1 AND email_verified = 1")
        row = cur.fetchone()
        fully_verified = row["count"] if row else 0

        cur.execute("SELECT COUNT(*) AS count FROM students WHERE phone_verified = 1 OR email_verified = 1")
        row = cur.fetchone()
        partially_verified = row["count"] if row else 0

        cur.execute("""
            SELECT department, COUNT(*) AS count 
            FROM students 
            GROUP BY department 
            ORDER BY count DESC
        """)
        dept_distribution = {r["department"]: r["count"] for r in cur.fetchall()}

        cur.execute("""
            SELECT 
                SUM(CASE WHEN phone_verified = 1 AND email_verified = 1 THEN 1 ELSE 0 END) AS both_ok,
                SUM(CASE WHEN phone_verified = 1 AND email_verified = 0 THEN 1 ELSE 0 END) AS phone_only,
                SUM(CASE WHEN phone_verified = 0 AND email_verified = 1 THEN 1 ELSE 0 END) AS email_only,
                SUM(CASE WHEN phone_verified = 0 AND email_verified = 0 THEN 1 ELSE 0 END) AS unverified
            FROM students
        """)
        v_row = cur.fetchone() or {}

        cur.execute("""
            SELECT CAST(created_at AS DATE) AS reg_date, COUNT(*) AS count 
            FROM students 
            GROUP BY CAST(created_at AS DATE) 
            ORDER BY reg_date DESC 
            LIMIT 7
        """)
        trend_rows = cur.fetchall()
        trends = [{"date": str(r["reg_date"]), "count": r["count"]} for r in reversed(trend_rows)]

    verification_rate = round((fully_verified / total_students * 100), 1) if total_students > 0 else 0.0

    return {
        "kpis": {
            "total_students": total_students,
            "fully_verified": fully_verified,
            "partially_verified": partially_verified,
            "verification_rate": verification_rate
        },
        "department_distribution": dept_distribution,
        "verification_breakdown": {
            "Fully Verified": v_row.get("both_ok") or 0,
            "Phone Only": v_row.get("phone_only") or 0,
            "Email Only": v_row.get("email_only") or 0,
            "Unverified": v_row.get("unverified") or 0
        },
        "registration_trend": trends
    }


@app.get("/api/students", tags=["Students"])
def get_students(
    search: Optional[str] = "",
    department: Optional[str] = "",
    status_filter: Optional[str] = "",
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100)
):
    """Retrieve filtered, searched, and paginated student records."""
    offset = (page - 1) * limit
    params = []
    where_clauses = ["1=1"]

    if search:
        search_clean = search.strip()
        where_clauses.append("(full_name LIKE ? OR email LIKE ? OR phone LIKE ?)")
        term = f"%{search_clean}%"
        params.extend([term, term, term])

    if department:
        where_clauses.append("department = ?")
        params.append(department.strip())

    if status_filter == "verified":
        where_clauses.append("phone_verified = 1 AND email_verified = 1")
    elif status_filter == "pending":
        where_clauses.append("(phone_verified = 0 OR email_verified = 0)")

    where_sql = " AND ".join(where_clauses)

    with get_db() as conn:
        cur = conn.cursor()

        cur.execute(f"SELECT COUNT(*) AS count FROM students WHERE {where_sql}", params)
        count_row = cur.fetchone()
        total_records = count_row["count"] if count_row else 0

        cur.execute(f"""
            SELECT id, full_name, email, phone, department, semester, phone_verified, email_verified, approval_status, created_at
            FROM students
            WHERE {where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """, (*params, limit, offset))

        students = [dict(r) for r in cur.fetchall()]

    total_pages = (total_records + limit - 1) // limit if total_records > 0 else 1

    return {
        "total": total_records,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "students": students
    }


# ---------------------------------------------------------
# Modular Routers Mounting (Student Portal & Admin Portal)
# ---------------------------------------------------------
app.include_router(student_router)
app.include_router(admin_router)


# ---------------------------------------------------------
# Direct Local Run Helper
# ---------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=settings.DEBUG)
