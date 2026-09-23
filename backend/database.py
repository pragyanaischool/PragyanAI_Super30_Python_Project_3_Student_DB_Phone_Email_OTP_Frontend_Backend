"""Database connection and lifecycle manager.

Provides dual-engine compatibility for SQLite (local development) and
PostgreSQL (Render managed database), including pooled connections, dynamic schema
initialization, connection pooling context management, and row-dict mapping.
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
            
            # If query is an INSERT and doesn't specify RETURNING, append RETURNING id for lastrowid compatibility
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


def init_db() -> None:
    """Initializes tables and indexes, executing each DDL statement individually."""
    with get_db() as conn:
        cursor = conn.cursor()

        if IS_POSTGRES:
            statements = [
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
                    name VARCHAR(150) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    phone VARCHAR(50) UNIQUE NOT NULL,
                    department VARCHAR(100) NOT NULL,
                    semester INT CHECK (semester BETWEEN 1 AND 8),
                    phone_verified SMALLINT DEFAULT 0 CHECK (phone_verified IN (0, 1)),
                    email_verified SMALLINT DEFAULT 0 CHECK (email_verified IN (0, 1)),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                "CREATE INDEX IF NOT EXISTS idx_students_email ON students(email);",
                "CREATE INDEX IF NOT EXISTS idx_students_phone ON students(phone);",
                "CREATE INDEX IF NOT EXISTS idx_students_dept ON students(department);"
            ]
        else:
            statements = [
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
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    phone TEXT UNIQUE NOT NULL,
                    department TEXT NOT NULL,
                    semester INTEGER CHECK (semester BETWEEN 1 AND 8),
                    phone_verified INTEGER DEFAULT 0 CHECK (phone_verified IN (0, 1)),
                    email_verified INTEGER DEFAULT 0 CHECK (email_verified IN (0, 1)),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                "CREATE INDEX IF NOT EXISTS idx_students_email ON students(email);",
                "CREATE INDEX IF NOT EXISTS idx_students_phone ON students(phone);",
                "CREATE INDEX IF NOT EXISTS idx_students_dept ON students(department);"
            ]

        for stmt in statements:
            cursor.execute(stmt.strip())

        conn.commit()


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
