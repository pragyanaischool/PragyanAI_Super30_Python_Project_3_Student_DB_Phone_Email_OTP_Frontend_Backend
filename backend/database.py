"""Database Connection, Migration, and Lifecycle Manager.

Provides dual-engine compatibility for SQLite (local development) and
PostgreSQL (Render managed database), including pooled connections, dynamic schema
initialization, safe sequential column migrations, legacy column relaxation,
and dynamic foreign key seed resolution.
"""

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator, Any, Dict, List, Optional
from config import settings

# Determine database engine from DATABASE_URL
DB_URL = settings.DATABASE_URL
IS_POSTGRES = DB_URL.startswith("postgresql://") or DB_URL.startswith("postgres://")

_PG_POOL = None

if IS_POSTGRES:
    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor

    # Normalize Render 'postgres://' connection scheme to 'postgresql://'
    if DB_URL.startswith("postgres://"):
        DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

    try:
        # Initialize thread-safe connection pool for PostgreSQL
        _PG_POOL = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=DB_URL
        )
    except Exception as e:
        print(f"[!] Warning: Could not initialize PostgreSQL pool immediately: {e}")


class UnifiedCursor:
    """Cursor wrapper that transparently adapts parameter placeholders between
    SQLite ('?') and PostgreSQL ('%s'), supports dict rows, iteration, and RETURNING.
    """

    def __init__(self, raw_cursor, is_postgres: bool):
        self._cursor = raw_cursor
        self._is_postgres = is_postgres
        self._last_inserted_id = None

    def execute(self, query: str, params: Optional[tuple] = None):
        sql = query
        if self._is_postgres:
            if "?" in sql and "%s" not in sql:
                sql = sql.replace("?", "%s")

            stripped = sql.strip().rstrip(";").strip()
            if stripped.upper().startswith("INSERT INTO") and "RETURNING" not in stripped.upper():
                sql = f"{stripped} RETURNING id;"
                result = self._cursor.execute(sql, params or ())
                try:
                    row = self._cursor.fetchone()
                    if row and "id" in row:
                        self._last_inserted_id = row["id"]
                except Exception:
                    self._last_inserted_id = None
                return result

            return self._cursor.execute(sql, params or ())
        else:
            if "%s" in sql and "?" not in sql:
                sql = sql.replace("%s", "?")
            res = self._cursor.execute(sql, params or ())
            self._last_inserted_id = self._cursor.lastrowid
            return res

    def executemany(self, query: str, seq_of_params):
        sql = query
        if self._is_postgres:
            if "?" in sql and "%s" not in sql:
                sql = sql.replace("?", "%s")
            return self._cursor.executemany(sql, seq_of_params)
        else:
            if "%s" in sql and "?" not in sql:
                sql = sql.replace("%s", "?")
            return self._cursor.executemany(sql, seq_of_params)

    def fetchone(self) -> Optional[Dict[str, Any]]:
        row = self._cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self) -> List[Dict[str, Any]]:
        rows = self._cursor.fetchall()
        return [dict(r) for r in rows]

    def fetchmany(self, size: int = 1) -> List[Dict[str, Any]]:
        rows = self._cursor.fetchmany(size)
        return [dict(r) for r in rows]

    def __iter__(self):
        for row in self._cursor:
            yield dict(row)

    @property
    def lastrowid(self) -> Optional[int]:
        if self._is_postgres:
            return self._last_inserted_id
        return self._cursor.lastrowid

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        self._cursor.close()


class UnifiedConnection:
    """Connection wrapper ensuring uniform commit, rollback, and cursor operations."""

    def __init__(self, raw_connection, is_postgres: bool, is_pooled: bool = False):
        self._connection = raw_connection
        self._is_postgres = is_postgres
        self._is_pooled = is_pooled

    def cursor(self) -> UnifiedCursor:
        if self._is_postgres:
            return UnifiedCursor(self._connection.cursor(cursor_factory=RealDictCursor), is_postgres=True)
        return UnifiedCursor(self._connection.cursor(), is_postgres=False)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        if self._is_postgres and self._is_pooled and _PG_POOL:
            _PG_POOL.putconn(self._connection)
        else:
            self._connection.close()


def get_raw_connection() -> UnifiedConnection:
    """Establishes or acquires an active connection to the designated database engine."""
    global _PG_POOL
    if IS_POSTGRES:
        if _PG_POOL is None:
            _PG_POOL = pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=DB_URL)
        raw_conn = _PG_POOL.getconn()
        return UnifiedConnection(raw_conn, is_postgres=True, is_pooled=True)
    else:
        if DB_URL.startswith("sqlite:///"):
            path = DB_URL.replace("sqlite:///", "")
        else:
            path = settings.DATABASE_PATH

        raw_conn = sqlite3.connect(path, timeout=15.0)
        raw_conn.execute("PRAGMA journal_mode=WAL;")
        raw_conn.execute("PRAGMA synchronous=NORMAL;")
        raw_conn.execute("PRAGMA foreign_keys=ON;")
        raw_conn.row_factory = sqlite3.Row
        return UnifiedConnection(raw_conn, is_postgres=False, is_pooled=False)


def _ensure_column_exists(cursor: UnifiedCursor, table: str, column: str, col_type: str):
    """Safely checks and adds a column if it does not exist without dropping tables."""
    try:
        if IS_POSTGRES:
            cursor.execute(f"""
                ALTER TABLE {table} 
                ADD COLUMN IF NOT EXISTS {column} {col_type};
            """)
        else:
            cursor.execute(f"PRAGMA table_info({table});")
            existing_cols = [row["name"] for row in cursor.fetchall()]
            if column not in existing_cols:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type};")
    except Exception as e:
        print(f"[!] Migration notice on {table}.{column}: {e}")


def _relax_legacy_not_null_constraints(cursor: UnifiedCursor):
    """Relaxes NOT NULL constraints on legacy columns (e.g. college_name, usn, branch)
    in existing PostgreSQL instances so new modular inserts do not fail.
    """
    if not IS_POSTGRES:
        return

    protected_columns = {"id", "email", "phone"}

    try:
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'students' 
              AND is_nullable = 'NO'
              AND column_default IS NULL;
        """)
        not_null_rows = cursor.fetchall()
        for row in not_null_rows:
            col = row.get("column_name")
            if col and col not in protected_columns:
                print(f"[*] Relaxing legacy NOT NULL constraint on column: students.{col}")
                cursor.execute(f"ALTER TABLE students ALTER COLUMN {col} DROP NOT NULL;")
    except Exception as err:
        print(f"[!] Warning during constraint relaxation: {err}")


def init_db() -> None:
    """Initializes tables, applies safe column migrations, creates indexes, and populates seed data."""
    with get_db() as conn:
        cursor = conn.cursor()

        # ---------------------------------------------------------
        # PHASE 1: Base Table Creation
        # ---------------------------------------------------------
        if IS_POSTGRES:
            table_statements = [
                """
                CREATE TABLE IF NOT EXISTS admins (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(50) DEFAULT 'superadmin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS students (
                    id SERIAL PRIMARY KEY,
                    full_name VARCHAR(150),
                    name VARCHAR(150),
                    email VARCHAR(255) UNIQUE NOT NULL,
                    phone VARCHAR(50) UNIQUE NOT NULL,
                    department VARCHAR(100),
                    semester INT DEFAULT 1,
                    bio TEXT DEFAULT '',
                    phone_verified BOOLEAN DEFAULT FALSE,
                    email_verified BOOLEAN DEFAULT FALSE,
                    approval_status VARCHAR(50) DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id SERIAL PRIMARY KEY,
                    topic VARCHAR(255) NOT NULL,
                    session_date VARCHAR(50) NOT NULL,
                    timing VARCHAR(100) NOT NULL,
                    mode VARCHAR(50) DEFAULT 'Online',
                    meeting_link VARCHAR(500) NOT NULL,
                    description TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS attendance (
                    id SERIAL PRIMARY KEY,
                    session_id INT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    student_id INT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                    status VARCHAR(50) DEFAULT 'SUBMITTED',
                    remarks TEXT DEFAULT '',
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT unique_session_student UNIQUE (session_id, student_id)
                );
                """
            ]
        else:
            table_statements = [
                """
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'superadmin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT,
                    name TEXT,
                    email TEXT UNIQUE NOT NULL,
                    phone TEXT UNIQUE NOT NULL,
                    department TEXT,
                    semester INTEGER DEFAULT 1,
                    bio TEXT DEFAULT '',
                    phone_verified BOOLEAN DEFAULT 0,
                    email_verified BOOLEAN DEFAULT 0,
                    approval_status TEXT DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    timing TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    meeting_link TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    student_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'SUBMITTED',
                    remarks TEXT DEFAULT '',
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                    UNIQUE(session_id, student_id)
                );
                """
            ]

        for stmt in table_statements:
            cursor.execute(stmt.strip())

        # ---------------------------------------------------------
        # PHASE 2: Dynamic Column Migrations & Constraint Relaxation
        # ---------------------------------------------------------
        _ensure_column_exists(cursor, "students", "full_name", "VARCHAR(150) DEFAULT ''")
        _ensure_column_exists(cursor, "students", "name", "VARCHAR(150) DEFAULT ''")
        _ensure_column_exists(cursor, "students", "department", "VARCHAR(100) DEFAULT 'General'")
        _ensure_column_exists(cursor, "students", "semester", "INT DEFAULT 1")
        _ensure_column_exists(cursor, "students", "bio", "TEXT DEFAULT ''")
        bool_type = "BOOLEAN DEFAULT FALSE" if IS_POSTGRES else "BOOLEAN DEFAULT 0"
        _ensure_column_exists(cursor, "students", "phone_verified", bool_type)
        _ensure_column_exists(cursor, "students", "email_verified", bool_type)
        _ensure_column_exists(cursor, "students", "approval_status", "VARCHAR(50) DEFAULT 'PENDING'")

        # Drop legacy NOT NULL constraints from abandoned columns
        _relax_legacy_not_null_constraints(cursor)

        # Sync legacy 'name' column to 'full_name' if needed
        try:
            cursor.execute("""
                UPDATE students 
                SET full_name = name 
                WHERE (full_name IS NULL OR full_name = '') AND name IS NOT NULL;
            """)
        except Exception:
            pass

        # ---------------------------------------------------------
        # PHASE 3: Create Indexes
        # ---------------------------------------------------------
        index_statements = [
            "CREATE INDEX IF NOT EXISTS idx_students_email ON students(email);",
            "CREATE INDEX IF NOT EXISTS idx_students_phone ON students(phone);",
            "CREATE INDEX IF NOT EXISTS idx_students_dept ON students(department);",
            "CREATE INDEX IF NOT EXISTS idx_students_approval ON students(approval_status);",
            "CREATE INDEX IF NOT EXISTS idx_attendance_session ON attendance(session_id);",
            "CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id);"
        ]
        for idx in index_statements:
            cursor.execute(idx.strip())

        # ---------------------------------------------------------
        # PHASE 4: Automated Seed Data (Dynamic Foreign Key Resolution)
        # ---------------------------------------------------------
        cursor.execute("SELECT COUNT(*) as count FROM students;")
        st_count_row = cursor.fetchone()
        st_count = st_count_row.get("count", 0) if st_count_row else 0

        if st_count == 0:
            sample_students = [
                (
                    "Sateesh Ambesange",
                    "Sateesh Ambesange",
                    "sateesh.ambesange@pragyanai.com",
                    "+919741007422",
                    "Computer Science",
                    8,
                    "AI Systems Architect & Founder focusing on Agentic AI, EDA, and Kernel Drivers.",
                    True,
                    True,
                    "APPROVED"
                ),
                (
                    "Rohan Kumar",
                    "Rohan Kumar",
                    "rohan.k@pragyanai.com",
                    "+919876543211",
                    "Artificial Intelligence",
                    6,
                    "Specializing in small language models, quantization, and ONNX Runtime execution.",
                    True,
                    True,
                    "APPROVED"
                ),
                (
                    "Priya Sharma",
                    "Priya Sharma",
                    "priya.s@pragyanai.com",
                    "+919876543212",
                    "Electronics",
                    6,
                    "Embedded Linux engineer researching real-time kernel optimizations and Yocto.",
                    True,
                    False,
                    "PENDING"
                ),
                (
                    "Ananya Patel",
                    "Ananya Patel",
                    "ananya.p@pragyanai.com",
                    "+919876543213",
                    "Information Tech",
                    4,
                    "Student focusing on distributed databases, vector indexes, and microservices.",
                    False,
                    False,
                    "REJECTED"
                ),
            ]
            cursor.executemany("""
                INSERT INTO students (
                    full_name, name, email, phone, department, semester, bio,
                    phone_verified, email_verified, approval_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, sample_students)

        # Check sessions table
        cursor.execute("SELECT COUNT(*) as count FROM sessions;")
        sess_count_row = cursor.fetchone()
        sess_count = sess_count_row.get("count", 0) if sess_count_row else 0

        if sess_count == 0:
            sample_sessions = [
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
                )
            ]
            cursor.executemany("""
                INSERT INTO sessions (
                    topic, session_date, timing, mode, meeting_link, description
                ) VALUES (?, ?, ?, ?, ?, ?);
            """, sample_sessions)

        # Check attendance table and seed using ACTUAL queried IDs
        cursor.execute("SELECT COUNT(*) as count FROM attendance;")
        att_count_row = cursor.fetchone()
        att_count = att_count_row.get("count", 0) if att_count_row else 0

        if att_count == 0:
            cursor.execute("SELECT id FROM sessions ORDER BY id ASC LIMIT 2;")
            available_sessions = [r["id"] for r in cursor.fetchall()]

            cursor.execute("SELECT id FROM students WHERE approval_status = 'APPROVED' ORDER BY id ASC LIMIT 2;")
            available_students = [r["id"] for r in cursor.fetchall()]

            # Fall back to any student if none are explicitly marked APPROVED yet
            if not available_students:
                cursor.execute("SELECT id FROM students ORDER BY id ASC LIMIT 2;")
                available_students = [r["id"] for r in cursor.fetchall()]

            if available_sessions and available_students:
                sample_attendance = []
                s_id = available_sessions[0]
                
                # First student marked PRESENT
                sample_attendance.append((
                    s_id, 
                    available_students[0], 
                    "PRESENT", 
                    "Active participant during live Q&A and code walkthrough."
                ))
                
                # Second student (if available) marked SUBMITTED
                if len(available_students) > 1:
                    sample_attendance.append((
                        s_id, 
                        available_students[1], 
                        "SUBMITTED", 
                        "Submitted via student portal; verification pending."
                    ))

                if IS_POSTGRES:
                    cursor.executemany("""
                        INSERT INTO attendance (
                            session_id, student_id, status, remarks
                        ) VALUES (?, ?, ?, ?)
                        ON CONFLICT (session_id, student_id) DO NOTHING;
                    """, sample_attendance)
                else:
                    cursor.executemany("""
                        INSERT OR IGNORE INTO attendance (
                            session_id, student_id, status, remarks
                        ) VALUES (?, ?, ?, ?);
                    """, sample_attendance)


@contextmanager
def get_db() -> Generator[UnifiedConnection, None, None]:
    """Context manager providing managed transactions: auto-commit on completion and rollback on error."""
    connection = get_raw_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    init_db()
    engine_name = "PostgreSQL" if IS_POSTGRES else "SQLite"
    print(f"Database initialized and migrated successfully using engine: {engine_name}")
