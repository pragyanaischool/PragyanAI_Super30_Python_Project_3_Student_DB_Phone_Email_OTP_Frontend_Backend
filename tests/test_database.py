import os
import sqlite3
import pytest
from backend.database import get_db, init_db

TEST_DB = "test_unit_students.db"


@pytest.fixture(autouse=True)
def setup_and_teardown_db(monkeypatch):
    """Creates an isolated temporary SQLite database for each test run."""
    monkeypatch.setattr("backend.config.settings.DATABASE_PATH", TEST_DB)
    monkeypatch.setattr("backend.database.settings.DATABASE_PATH", TEST_DB)
    
    # Initialize clean database schema
    init_db()
    
    yield
    
    # Cleanup after test completes
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if os.path.exists(f"{TEST_DB}-wal"):
        os.remove(f"{TEST_DB}-wal")
    if os.path.exists(f"{TEST_DB}-shm"):
        os.remove(f"{TEST_DB}-shm")


def test_schema_tables_exist():
    """Verify that admins and students tables are created."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row["name"] for row in cursor.fetchall()]
        assert "admins" in tables
        assert "students" in tables


def test_student_insert_and_retrieval():
    """Verify insertion and field mappings for a new student record."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO students (name, email, phone, department, semester)
            VALUES (?, ?, ?, ?, ?)
        """, ("Test User", "test.user@example.com", "+919876543210", "Computer Science", 3))
        conn.commit()

        cursor.execute("SELECT * FROM students WHERE email = ?", ("test.user@example.com",))
        student = cursor.fetchone()

        assert student is not None
        assert student["name"] == "Test User"
        assert student["phone"] == "+919876543210"
        assert student["department"] == "Computer Science"
        assert student["semester"] == 3
        assert student["phone_verified"] == 0
        assert student["email_verified"] == 0


def test_unique_constraint_enforcement():
    """Verify unique constraint on email and phone columns."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO students (name, email, phone, department, semester)
            VALUES (?, ?, ?, ?, ?)
        """, ("First User", "duplicate@example.com", "+911111111111", "AI", 1))
        conn.commit()

        # Duplicate email should fail
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO students (name, email, phone, department, semester)
                VALUES (?, ?, ?, ?, ?)
            """, ("Second User", "duplicate@example.com", "+912222222222", "Data Science", 2))
            conn.commit()

        # Duplicate phone should fail
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO students (name, email, phone, department, semester)
                VALUES (?, ?, ?, ?, ?)
            """, ("Third User", "unique@example.com", "+911111111111", "Information Tech", 4))
            conn.commit()


def test_semester_range_constraint():
    """Verify that semester values outside 1-8 trigger a CHECK constraint error."""
    with get_db() as conn:
        cursor = conn.cursor()
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO students (name, email, phone, department, semester)
                VALUES (?, ?, ?, ?, ?)
            """, ("Invalid Sem User", "invalidsem@example.com", "+913333333333", "Electronics", 9))
            conn.commit()
