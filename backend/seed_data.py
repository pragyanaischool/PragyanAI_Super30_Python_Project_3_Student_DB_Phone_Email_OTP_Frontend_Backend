"""Database Seeder Script.

Initializes tables and seeds:
- 1 Superadmin account
- 125 Student records across 5 academic departments with varying verification states

Fully compatible with both SQLite and PostgreSQL via the backend abstraction layer.
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


def hash_password(password: str) -> str:
    """Generates SHA-256 password hash for administrator credentials."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def seed_database():
    print("[*] Initializing database schema...")
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
        # 2. Student Records Seeding
        # -------------------------------------------------------------
        cursor.execute("SELECT COUNT(*) AS count FROM students")
        row = cursor.fetchone()
        current_student_count = row["count"] if row else 0

        target_total = 125
        needed = target_total - current_student_count

        if needed <= 0:
            print(f"[i] Student directory already contains {current_student_count} records (>= {target_total}). Skipping.")
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

                # Status distribution: ~50% verified, ~25% phone-only, ~15% email-only, ~10% unverified
                rand_val = random.random()
                if rand_val < 0.50:
                    phone_ver, email_ver = 1, 1
                elif rand_val < 0.75:
                    phone_ver, email_ver = 1, 0
                elif rand_val < 0.90:
                    phone_ver, email_ver = 0, 1
                else:
                    phone_ver, email_ver = 0, 0

                student_records.append((name, email, phone, dept, semester, phone_ver, email_ver))

            # Batch insert rows using unified parameter placeholders
            cursor.executemany("""
                INSERT INTO students (name, email, phone, department, semester, phone_verified, email_verified)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, student_records)

            conn.commit()
            print(f"[+] Successfully inserted {len(student_records)} student records.")

        # -------------------------------------------------------------
        # 3. Post-Seeding Health & Metrics Check
        # -------------------------------------------------------------
        cursor.execute("SELECT COUNT(*) AS total FROM students")
        total = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT
                SUM(CASE WHEN phone_verified = 1 AND email_verified = 1 THEN 1 ELSE 0 END) AS full_ver,
                SUM(CASE WHEN phone_verified = 0 AND email_verified = 0 THEN 1 ELSE 0 END) AS unverified
            FROM students
        """)
        diag = cursor.fetchone()

        print("\n" + "=" * 54)
        print("DATABASE POPULATION SUMMARY")
        print("=" * 54)
        print(f" Total Student Records  : {total}")
        print(f" Fully Verified (2-Step): {diag['full_ver'] or 0}")
        print(f" Unverified Records     : {diag['unverified'] or 0}")
        print(f" Superadmin Login       : admin / admin123")
        print("=" * 54 + "\n")


if __name__ == "__main__":
    try:
        seed_database()
    except Exception as err:
        print(f"[!] Seeding failed: {err}", file=sys.stderr)
        sys.exit(1)
