"""Comprehensive Database Seeder Script.

Initializes tables and seeds:
- 1 Superadmin administrative credential
- 125 Student records with realistic department bios, dual-channel verifications, and onboarding states
- 6 Scheduled Academic & Training Sessions (Online, Offline, Hybrid)
- 250+ Cross-referenced Session Attendance records with instructor evaluation remarks

Compatible with both SQLite and PostgreSQL via the UnifiedConnection abstraction layer.
"""

import os
import sys
from pathlib import Path

# Ensure project root is prioritized on sys.path before any package imports occur
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import hashlib
import random

# Internal imports with fallback handling
try:
    from backend.config import settings
    from backend.database import init_db, get_db
except ImportError:
    from config import settings
    from database import init_db, get_db

# Deterministic random seed for consistent sample data generation
random.seed(42)

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
    "Shaurya", "Atharva", "Dhruv", "Kabir", "Rudra", "Diya", "Saanvi", "Ananya", "Aadhya", "Pari",
    "Fatima", "Isha", "Anushka", "Myra", "Aarohi", "Navya", "Riya", "Kiara", "Kavya", "Tara",
    "Rohan", "Rahul", "Pooja", "Neha", "Vikram", "Suresh", "Manish", "Deepak", "Sneha", "Kriti",
    "Gaurav", "Simran", "Nikhil", "Meera", "Kunal", "Tanvi", "Abhishek", "Shweta", "Harsh", "Pragya"
]

LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Patel", "Mehta", "Reddy", "Nair", "Iyer", "Rao", "Kumar",
    "Singh", "Chauhan", "Joshi", "Mishra", "Pandey", "Bose", "Das", "Banerjee", "Chatterjee", "Bhat",
    "Kulkarni", "Deshmukh", "Patil", "Pillai", "Menon", "Saxena", "Soni", "Agarwal", "Bhardwaj", "Malhotra"
]

DEPARTMENTS = [
    "Computer Science",
    "Artificial Intelligence",
    "Data Science",
    "Information Tech",
    "Electronics"
]

DEPARTMENT_BIOS = {
    "Computer Science": [
        "Focusing on high-performance Linux kernel systems, distributed key-value stores, and C++.",
        "Undergraduate researching low-latency microservices, async FastAPI pipelines, and Docker.",
        "Developing graph traversal algorithms and distributed state management in Rust.",
        "Interested in network protocols, socket programming, and database internals."
    ],
    "Artificial Intelligence": [
        "Researching cyclic state machines in LangGraph, tool calling agents, and evaluation benchmarks.",
        "Specializing in quantization, ONNX Runtime inference, and small language model fine-tuning.",
        "Building multi-agent autonomous negotiation systems and tool-augmented LLM pipelines.",
        "Exploring multimodal vision-language models and reinforcement learning from human feedback."
    ],
    "Data Science": [
        "Working on feature store pipelines, streaming embeddings, and time-series forecasting.",
        "Focusing on approximate nearest neighbors, vector search indexing, and dense retrieval.",
        "Researching Bayesian neural networks, predictive regression, and automated anomaly detection.",
        "Building end-to-end data lineage systems and distributed preprocessing jobs."
    ],
    "Information Tech": [
        "Cloud infrastructure specialist focusing on Kubernetes operators and CI/CD pipelines.",
        "Researching zero-trust network architectures, micro-segmentation, and web security.",
        "Specializing in high-availability distributed storage, Ceph, and automated infra-as-code.",
        "Developing serverless event-driven architectures and scalable message broker pipelines."
    ],
    "Electronics": [
        "Embedded Linux engineer researching real-time kernel optimizations, Yocto, and drivers.",
        "Working on automated computer vision defect verification for printed circuit board traces.",
        "Specializing in SystemVerilog, FPGA acceleration, and automated RTL testbenches.",
        "Profiling NPU inference latency and hardware accelerator DMA transfers."
    ]
}

ACADEMIC_SESSIONS = [
    (
        "Agentic AI Architecture & Multi-Agent LangGraph Systems",
        "2026-10-01",
        "10:00 AM - 12:30 PM",
        "Online",
        "https://meet.google.com/abc-prag-xyz",
        "Architecture patterns for cyclic graphs, persistent state checkpoints, human-in-the-loop workflows, and dynamic tool orchestration."
    ),
    (
        "Linux Kernel Drivers & Edge AI Acceleration",
        "2026-10-04",
        "02:00 PM - 04:30 PM",
        "Hybrid",
        "Lab 4B / https://meet.google.com/def-prag-uvw",
        "Writing character device drivers, handling DMA transfers, interrupt handlers, and profiling NPU inferencing latency."
    ),
    (
        "High-Throughput FastAPI Microservices & Event Streams",
        "2026-10-08",
        "11:00 AM - 01:00 PM",
        "Online",
        "https://meet.google.com/ghi-prag-rst",
        "Building resilient async REST endpoints, Server-Sent Events (SSE), connection pooling, and Docker production deployments."
    ),
    (
        "Computer Vision for Automated PCB Defect Inspection",
        "2026-10-12",
        "03:00 PM - 05:30 PM",
        "Hybrid",
        "Lab 2A / https://meet.google.com/jkl-prag-mno",
        "Convolutional feature extraction, contour verification, trace continuity testing, and synthetic defect augmentation."
    ),
    (
        "Distributed Vector Search & Enterprise Retrieval-Augmented Generation",
        "2026-10-16",
        "10:30 AM - 01:00 PM",
        "Online",
        "https://meet.google.com/pqr-prag-stu",
        "Dense and sparse hybrid search, re-ranking strategies, chunking semantics, and FAISS/Qdrant cluster deployment."
    ),
    (
        "Automated Register-Transfer Level (RTL) Design & Verification",
        "2026-10-20",
        "02:30 PM - 05:00 PM",
        "Online",
        "https://meet.google.com/vwx-prag-yza",
        "Verilog/SystemVerilog design methodologies, automated testbench generation, functional coverage, and LLM-assisted linting."
    )
]

ATTENDANCE_REMARKS_POOL = {
    "PRESENT": [
        "Active participant during live Q&A and code walkthrough.",
        "Verified on stream; completed all hands-on exercises.",
        "Demonstrated working implementation during breakout review.",
        "Answered quiz questions accurately; verified on call.",
        "Submitted lab exercise and hardware log file on time.",
        "Contributed insightful architecture questions during lecture."
    ],
    "SUBMITTED": [
        "Self-submitted via student dashboard; awaiting review.",
        "Attendance logged by student; notebook validation in progress.",
        "Self-service check-in recorded; verifying meeting attendance logs."
    ],
    "ABSENT": [
        "Did not connect to session Google Meet or classroom room.",
        "Unexcused absence; no participation recorded.",
        "Session link not joined.",
        "Left meeting within first 10 minutes without notice."
    ]
}


def hash_password(password: str) -> str:
    """Generates SHA-256 password hash for administrator credentials."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def seed_database():
    print("[*] Initializing database schema and ensuring tables exist...")
    init_db()

    with get_db() as conn:
        cursor = conn.cursor()

        # -------------------------------------------------------------
        # 1. Superadmin Seeding (Idempotent)
        # -------------------------------------------------------------
        admin_username = "admin"
        admin_email = "admin@eduportal.ac.in"
        admin_password_hash = hash_password("admin123")

        cursor.execute("SELECT id FROM admins WHERE username = ? OR email = ?", (admin_username, admin_email))
        existing_admin = cursor.fetchone()

        if not existing_admin:
            cursor.execute("""
                INSERT INTO admins (username, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            """, (admin_username, admin_email, admin_password_hash, "superadmin"))
            print(f"[+] Admin account created -> Username: '{admin_username}', Password: 'admin123'")
        else:
            print("[i] Superadmin account already exists. Skipping insertion.")

        # -------------------------------------------------------------
        # 2. Student Records Seeding (Target: 125 Students)
        # -------------------------------------------------------------
        cursor.execute("SELECT COUNT(*) AS count FROM students")
        row = cursor.fetchone()
        current_student_count = row["count"] if row else 0

        target_total = 125
        needed = target_total - current_student_count

        if needed <= 0:
            print(f"[i] Student directory already contains {current_student_count} records (>= {target_total}).")
        else:
            print(f"[*] Seeding {needed} new student records to reach {target_total} total...")

            existing_emails = set()
            existing_phones = set()

            cursor.execute("SELECT email, phone FROM students")
            for record in cursor.fetchall():
                existing_emails.add(record["email"])
                existing_phones.add(record["phone"])

            student_records = []

            for i in range(1, needed + 1):
                first = random.choice(FIRST_NAMES)
                last = random.choice(LAST_NAMES)
                name = f"{first} {last}"

                # Generate unique email address
                slug = f"{first.lower()}.{last.lower()}{current_student_count + i}"
                email = f"{slug}@student.edu"
                while email in existing_emails:
                    email = f"{slug}.{random.randint(10, 999)}@student.edu"
                existing_emails.add(email)

                # Generate unique phone number (+91 prefix)
                phone_tail = f"{random.randint(6000000000, 9999999999)}"
                phone = f"+91{phone_tail}"
                while phone in existing_phones:
                    phone = f"+91{random.randint(6000000000, 9999999999)}"
                existing_phones.add(phone)

                dept = random.choice(DEPARTMENTS)
                semester = random.randint(1, 8)
                bio = random.choice(DEPARTMENT_BIOS[dept])

                # Realistic distribution:
                # 65% fully verified -> APPROVED
                # 20% partially verified -> PENDING
                # 15% unverified / stale -> REJECTED
                rand_val = random.random()
                if rand_val < 0.65:
                    phone_ver, email_ver = 1, 1
                    approval_status = "APPROVED"
                elif rand_val < 0.85:
                    if random.random() < 0.5:
                        phone_ver, email_ver = 1, 0
                    else:
                        phone_ver, email_ver = 0, 1
                    approval_status = "PENDING"
                else:
                    phone_ver, email_ver = 0, 0
                    approval_status = "REJECTED"

                student_records.append((
                    name, name, email, phone, dept, semester, bio,
                    phone_ver, email_ver, approval_status
                ))

            # Batch insert rows
            cursor.executemany("""
                INSERT INTO students (
                    full_name, name, email, phone, department, semester, bio,
                    phone_verified, email_verified, approval_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, student_records)

            conn.commit()
            print(f"[+] Successfully inserted {len(student_records)} new student profiles.")

        # -------------------------------------------------------------
        # 3. Academic Sessions Seeding (6 Detailed Sessions)
        # -------------------------------------------------------------
        cursor.execute("SELECT COUNT(*) AS count FROM sessions")
        sess_row = cursor.fetchone()
        session_count = sess_row["count"] if sess_row else 0

        if session_count == 0:
            print("[*] Seeding 6 published curriculum sessions...")
            cursor.executemany("""
                INSERT INTO sessions (
                    topic, session_date, timing, mode, meeting_link, description
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, ACADEMIC_SESSIONS)
            conn.commit()
            print("[+] Successfully published 6 academic curriculum sessions.")
        else:
            print(f"[i] Academic sessions already contain {session_count} records.")

        # -------------------------------------------------------------
        # 4. Session Attendance Records Seeding
        # -------------------------------------------------------------
        cursor.execute("SELECT COUNT(*) AS count FROM attendance")
        att_row = cursor.fetchone()
        attendance_count = att_row["count"] if att_row else 0

        if attendance_count < 20:
            print("[*] Generating cross-referenced attendance roster records...")

            cursor.execute("SELECT id FROM students WHERE approval_status = 'APPROVED'")
            approved_students = [r["id"] for r in cursor.fetchall()]

            cursor.execute("SELECT id FROM sessions")
            session_ids = [r["id"] for r in cursor.fetchall()]

            if approved_students and session_ids:
                attendance_records = []
                for s_id in session_ids:
                    # Select a sample of 35 to 55 approved students per session
                    sample_size = min(len(approved_students), random.randint(35, 55))
                    chosen_students = random.sample(approved_students, sample_size)

                    for st_id in chosen_students:
                        # 70% Present, 15% Submitted, 15% Absent
                        att_rand = random.random()
                        if att_rand < 0.70:
                            status_val = "PRESENT"
                        elif att_rand < 0.85:
                            status_val = "SUBMITTED"
                        else:
                            status_val = "ABSENT"

                        remark = random.choice(ATTENDANCE_REMARKS_POOL[status_val])
                        attendance_records.append((s_id, st_id, status_val, remark))

                cursor.executemany("""
                    INSERT INTO attendance (session_id, student_id, status, remarks)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(session_id, student_id) DO NOTHING
                """, attendance_records)

                conn.commit()
                print(f"[+] Successfully inserted {len(attendance_records)} attendance evaluations.")

        # -------------------------------------------------------------
        # 5. Post-Seeding Health & Metrics Check
        # -------------------------------------------------------------
        cursor.execute("SELECT COUNT(*) AS total FROM students")
        total_students = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT
                SUM(CASE WHEN approval_status = 'APPROVED' THEN 1 ELSE 0 END) AS approved_cnt,
                SUM(CASE WHEN approval_status = 'PENDING' THEN 1 ELSE 0 END) AS pending_cnt,
                SUM(CASE WHEN approval_status = 'REJECTED' THEN 1 ELSE 0 END) AS rejected_cnt,
                SUM(CASE WHEN phone_verified = 1 AND email_verified = 1 THEN 1 ELSE 0 END) AS full_ver,
                SUM(CASE WHEN phone_verified = 0 AND email_verified = 0 THEN 1 ELSE 0 END) AS unverified
            FROM students
        """)
        diag = cursor.fetchone()

        cursor.execute("SELECT COUNT(*) AS total_sess FROM sessions")
        total_sessions = cursor.fetchone()["total_sess"]

        cursor.execute("SELECT COUNT(*) AS total_att FROM attendance")
        total_attendance = cursor.fetchone()["total_att"]

        print("\n" + "=" * 60)
        print("PRAGYANAI DATABASE POPULATION SUMMARY")
        print("=" * 60)
        print(f" Total Student Records     : {total_students}")
        print(f" ├─ Approved for Sessions  : {diag['approved_cnt'] or 0}")
        print(f" ├─ Pending Onboarding     : {diag['pending_cnt'] or 0}")
        print(f" └─ Rejected Applications  : {diag['rejected_cnt'] or 0}")
        print(f" Fully Verified (SMS+Email): {diag['full_ver'] or 0}")
        print(f" Published Sessions        : {total_sessions}")
        print(f" Total Attendance Records  : {total_attendance}")
        print(f" Admin Credentials         : admin / admin123")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        seed_database()
    except Exception as err:
        print(f"[!] Seeding failed: {err}", file=sys.stderr)
        sys.exit(1)
