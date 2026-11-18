# tests/test_upload.py
import tempfile
from unittest.mock import Mock, patch, MagicMock
from clipper.upload import InstagramUploader

def test_login_creates_session_file():
    with tempfile.TemporaryDirectory() as tmp:
        session_path = f"{tmp}/session.json"
        db_path = f"{tmp}/clips.db"
        
        with patch("clipper.upload.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.login.return_value = True
            
            uploader = InstagramUploader("user", "pass", session_path, db_path, {})
            uploader.login()
            
            mock_client.login.assert_called_once_with("user", "pass")
            mock_client.dump_settings.assert_called_once_with(session_path)

def test_process_pending_uploads_one_clip():
    with tempfile.TemporaryDirectory() as tmp:
        session_path = f"{tmp}/session.json"
        db_path = f"{tmp}/clips.db"
        
        with patch("clipper.upload.Client") as mock_client_cls, \
             patch("clipper.video_check.validate_reels_spec", return_value=(True, "")), \
             patch("clipper.caption.generate_caption", return_value="test caption #hashtag"):
            
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.clip_upload.return_value = Mock(pk="ig_media_123")
            
            from clipper.db import init_db, register_clip
            conn = init_db(db_path)
            register_clip(conn, "clips/test.mp4", "clips/test.json")
            
            uploader = InstagramUploader("user", "pass", session_path, db_path, {
                "daily_limit": 25,
                "caption_template": "{top_phrase}",
                "fallback_hashtags": [],
                "max_hashtags": 30
            })
            uploader.client = mock_client
            
            count = uploader.process_pending()
            
            assert count == 1
            mock_client.clip_upload.assert_called_once()
            row = conn.execute("SELECT uploaded_at, instagram_id FROM clips WHERE id=1").fetchone()
            assert row[0] is not None
            assert row[1] == "ig_media_123"
            
            # Close connections to allow temp dir cleanup on Windows
            uploader.close()
            conn.close()