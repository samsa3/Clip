"""SQLite database module for clip tracking."""

import sqlite3
from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class ClipRow:
    id: int
    file_path: str
    meta_path: str
    file_hash: Optional[str]
    uploaded_at: Optional[str]
    instagram_id: Optional[str]
    caption: Optional[str]
    error: Optional[str]
    attempts: int
    created_at: str


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize the database, creating tables and indexes if they don't exist.
    
    Returns a connection with row_factory set to sqlite3.Row for named column access.
    """
    # Ensure directory exists
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL UNIQUE,
            meta_path TEXT NOT NULL,
            file_hash TEXT,
            uploaded_at TEXT,
            instagram_id TEXT,
            caption TEXT,
            error TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_clips_uploaded_at 
        ON clips(uploaded_at)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_clips_created_at 
        ON clips(created_at)
    """)
    
    conn.commit()
    return conn


def register_clip(conn_or_path, file_path: str, meta_path: str) -> int:
    """Register a new clip in the database.
    
    Uses INSERT OR IGNORE for idempotency on the unique file_path constraint.
    Returns the clip_id (lastrowid for new inserts, existing id for duplicates).
    
    Args:
        conn_or_path: Either a sqlite3.Connection or a database path string
        file_path: Path to the video file
        meta_path: Path to the metadata JSON file
    """
    # Handle both connection and path
    if isinstance(conn_or_path, str):
        # Create temporary connection
        conn = init_db(conn_or_path)
        close_after = True
    else:
        conn = conn_or_path
        close_after = False
    
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO clips (file_path, meta_path) VALUES (?, ?)",
            (file_path, meta_path)
        )
        conn.commit()
        
        if cursor.lastrowid:
            return cursor.lastrowid
        
        # If it was a duplicate, fetch the existing id
        row = conn.execute(
            "SELECT id FROM clips WHERE file_path = ?", (file_path,)
        ).fetchone()
        return row[0] if row else 0
    finally:
        if close_after:
            conn.close()


def get_pending(conn: sqlite3.Connection, limit: int = 25) -> list[ClipRow]:
    """Get clips that haven't been uploaded yet, ordered by creation time."""
    rows = conn.execute(
        "SELECT * FROM clips WHERE uploaded_at IS NULL ORDER BY created_at LIMIT ?",
        (limit,)
    ).fetchall()
    
    return [
        ClipRow(
            id=row["id"],
            file_path=row["file_path"],
            meta_path=row["meta_path"],
            file_hash=row["file_hash"],
            uploaded_at=row["uploaded_at"],
            instagram_id=row["instagram_id"],
            caption=row["caption"],
            error=row["error"],
            attempts=row["attempts"],
            created_at=row["created_at"]
        )
        for row in rows
    ]


def mark_uploaded(conn: sqlite3.Connection, clip_id: int, instagram_id: str, caption: str) -> None:
    """Mark a clip as successfully uploaded."""
    conn.execute(
        """
        UPDATE clips 
        SET uploaded_at = CURRENT_TIMESTAMP, 
            instagram_id = ?, 
            caption = ?, 
            attempts = attempts + 1
        WHERE id = ?
        """,
        (instagram_id, caption, clip_id)
    )
    conn.commit()


def mark_failed(conn: sqlite3.Connection, clip_id: int, error: str) -> None:
    """Mark a clip as failed with an error message."""
    conn.execute(
        """
        UPDATE clips 
        SET error = ?, 
            attempts = attempts + 1
        WHERE id = ?
        """,
        (error, clip_id)
    )
    conn.commit()