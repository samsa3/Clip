# tests/test_db.py
import tempfile
import sqlite3
from clipper.db import init_db, register_clip, get_pending, mark_uploaded, mark_failed, ClipRow

def test_register_and_fetch_pending():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = init_db(db_path)
    clip_id = register_clip(conn, "clips/clip_20240115_143022_001.mp4", "clips/clip_20240115_143022_001.json")
    pending = get_pending(conn)
    assert len(pending) == 1
    assert pending[0].id == clip_id
    assert pending[0].file_path == "clips/clip_20240115_143022_001.mp4"
    assert pending[0].uploaded_at is None

def test_mark_uploaded_removes_from_pending():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = init_db(db_path)
    clip_id = register_clip(conn, "clips/clip_20240115_143022_001.mp4", "clips/clip_20240115_143022_001.json")
    mark_uploaded(conn, clip_id, "ig_media_123", "test caption")
    pending = get_pending(conn)
    assert len(pending) == 0
    row = conn.execute("SELECT uploaded_at, instagram_id, caption FROM clips WHERE id=?", (clip_id,)).fetchone()
    assert row[0] is not None
    assert row[1] == "ig_media_123"
    assert row[2] == "test caption"

def test_mark_failed_increments_attempts():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = init_db(db_path)
    clip_id = register_clip(conn, "clips/clip_20240115_143022_001.mp4", "clips/clip_20240115_143022_001.json")
    mark_failed(conn, clip_id, "some error")
    row = conn.execute("SELECT attempts, error FROM clips WHERE id=?", (clip_id,)).fetchone()
    assert row[0] == 1
    assert row[1] == "some error"