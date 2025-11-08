# queuectl/database.py
import sqlite3
import os
from pathlib import Path

DB_DIR = Path.home() / ".queuectl"
DB_PATH = DB_DIR / "queue.db"

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def initialize_database():
    """Creates the necessary tables if they don't exist."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            command TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            retry_limit INTEGER NOT NULL DEFAULT 3,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            next_run_at TEXT DEFAULT NULL
        );
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_pending_next_run
        ON jobs (state, next_run_at);
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('max_retries', '3')")
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('backoff_base_seconds', '2')")
        
        conn.commit()
    print(f"Database initialized at: {DB_PATH}")