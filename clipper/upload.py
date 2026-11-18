"""Instagram uploader core with rate limiting, retries, and session management."""

import sqlite3
import time
import os
import logging
from typing import Optional
from dataclasses import dataclass
from pathlib import Path

# instagrapi will be imported lazily to allow testing without it
Client = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    success: bool
    instagram_id: Optional[str] = None
    error: Optional[str] = None


class InstagramUploader:
    """Handles Instagram Reels upload with rate limiting and retry logic."""
    
    def __init__(
        self,
        username: str,
        password: str,
        session_path: str,
        db_path: str,
        config: dict
    ):
        self.username = username
        self.password = password
        self.session_path = session_path
        self.db_path = db_path
        self.config = config
        self._client = None
        self._conn = None
        
        # Rate limiting
        self._last_upload_time = 0
        self._min_upload_interval = 60  # seconds (1 per minute)
        
    def _get_client(self):
        """Lazy-load instagrapi Client."""
        global Client
        if Client is None:
            from instagrapi import Client as InstaClient
            from instagrapi.exceptions import (
                ChallengeRequired, FeedbackRequired, PleaseWaitFewMinutes,
                LoginRequired, ClientError
            )
            Client = InstaClient
            # Store exception classes for use
            self.ChallengeRequired = ChallengeRequired
            self.FeedbackRequired = FeedbackRequired
            self.PleaseWaitFewMinutes = PleaseWaitFewMinutes
            self.LoginRequired = LoginRequired
            self.ClientError = ClientError
        return Client
    
    @property
    def client(self):
        """Get the instagrapi client, initializing if needed."""
        if self._client is None:
            Client = self._get_client()
            self._client = Client()
        return self._client
    
    @client.setter
    def client(self, value):
        self._client = value
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            from clipper.db import init_db
            self._conn = init_db(self.db_path)
        return self._conn
    
    def login(self) -> None:
        """Login to Instagram, using session file if available."""
        Client = self._get_client()
        
        if self._client is None:
            self._client = Client()
        
        # Load session if exists
        if os.path.exists(self.session_path):
            logger.info(f"Loading session from {self.session_path}")
            try:
                self._client.load_settings(self.session_path)
                self._client.login(self.username, self.password)
                logger.info("Session loaded and login successful")
                return
            except Exception as e:
                logger.warning(f"Failed to load session: {e}, will do fresh login")
        
        # Fresh login
        logger.info(f"Logging in as {self.username}")
        self._client.login(self.username, self.password)
        
        # Save session
        os.makedirs(os.path.dirname(os.path.abspath(self.session_path)), exist_ok=True)
        self._client.dump_settings(self.session_path)
        logger.info(f"Session saved to {self.session_path}")
    
    def _rate_limit(self) -> None:
        """Enforce minimum interval between uploads."""
        elapsed = time.time() - self._last_upload_time
        if elapsed < self._min_upload_interval:
            sleep_time = self._min_upload_interval - elapsed
            logger.info(f"Rate limiting: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self._last_upload_time = time.time()
    
    def _check_daily_limit(self) -> int:
        """Check how many clips uploaded today. Returns count."""
        conn = self._get_connection()
        today = time.strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT COUNT(*) FROM clips WHERE uploaded_at IS NOT NULL AND date(uploaded_at) = ?",
            (today,)
        ).fetchone()
        return row[0] if row else 0
    
    def _upload_with_retry(self, file_path: str, caption: str, max_retries: int = 3) -> UploadResult:
        """Upload a single clip with retry logic."""
        Client = self._get_client()
        
        for attempt in range(max_retries):
            try:
                self._rate_limit()
                media = self._client.clip_upload(file_path, caption)
                return UploadResult(success=True, instagram_id=media.pk)
                
            except self.ChallengeRequired as e:
                logger.error(f"Challenge required: {e}")
                return UploadResult(success=False, error=f"Challenge required: {e}")
                
            except self.FeedbackRequired as e:
                logger.error(f"Feedback required: {e}")
                return UploadResult(success=False, error=f"Feedback required: {e}")
                
            except self.PleaseWaitFewMinutes as e:
                wait_time = 60 * (attempt + 1) * 5  # 5, 10, 15 minutes
                logger.warning(f"Rate limited by Instagram, waiting {wait_time}s: {e}")
                time.sleep(wait_time)
                continue
                
            except self.LoginRequired as e:
                logger.warning(f"Login required, re-authenticating: {e}")
                try:
                    self.login()
                    continue  # Retry after re-login
                except Exception as login_err:
                    return UploadResult(success=False, error=f"Re-login failed: {login_err}")
                
            except self.ClientError as e:
                # Check for HTTP 429 in error message
                if "429" in str(e) or "rate limit" in str(e).lower():
                    wait_time = 60 * (attempt + 1) * 2
                    logger.warning(f"Rate limit (429), waiting {wait_time}s: {e}")
                    time.sleep(wait_time)
                    continue
                logger.error(f"Client error: {e}")
                return UploadResult(success=False, error=f"Client error: {e}")
                
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    return UploadResult(success=False, error=f"Unexpected error: {e}")
                time.sleep(2 ** attempt)  # Exponential backoff: 1, 2, 4 seconds
        
        return UploadResult(success=False, error="Max retries exceeded")
    
    def process_pending(self) -> int:
        """Process all pending clips up to daily limit.
        
        Returns:
            Number of clips successfully uploaded in this cycle.
        """
        from clipper.db import get_pending, mark_uploaded, mark_failed
        from clipper.caption import generate_caption
        from clipper.video_check import validate_reels_spec
        
        conn = self._get_connection()
        
        # Check daily limit
        daily_uploaded = self._check_daily_limit()
        daily_limit = self.config.get("daily_limit", 25)
        
        if daily_uploaded >= daily_limit:
            logger.info(f"Daily limit reached ({daily_uploaded}/{daily_limit})")
            return 0
        
        remaining_today = daily_limit - daily_uploaded
        
        # Get pending clips
        pending = get_pending(conn, limit=remaining_today)
        
        if not pending:
            logger.info("No pending clips to upload")
            return 0
        
        logger.info(f"Processing {len(pending)} pending clips (daily: {daily_uploaded}/{daily_limit})")
        
        uploaded_count = 0
        
        for clip in pending:
            # Validate video spec
            ok, err = validate_reels_spec(clip.file_path)
            if not ok:
                logger.error(f"Video spec validation failed for {clip.file_path}: {err}")
                mark_failed(conn, clip.id, f"video spec: {err}")
                continue
            
            # Generate caption
            caption = generate_caption(
                clip.meta_path,
                self.config.get("caption_template", "{top_phrase}"),
                self.config.get("fallback_hashtags", []),
                self.config.get("max_hashtags", 30)
            )
            
            # Upload
            result = self._upload_with_retry(clip.file_path, caption)
            
            if result.success:
                mark_uploaded(conn, clip.id, result.instagram_id, caption)
                uploaded_count += 1
                logger.info(f"Uploaded clip {clip.id} as {result.instagram_id}")
            else:
                mark_failed(conn, clip.id, result.error or "Unknown error")
                logger.error(f"Failed to upload clip {clip.id}: {result.error}")
                
                # If it's a permanent failure (challenge, feedback), stop processing
                if "challenge required" in (result.error or "").lower() or \
                   "feedback required" in (result.error or "").lower():
                    logger.error("Permanent failure detected, stopping cycle")
                    break
        
        return uploaded_count
    
    @property
    def daily_uploaded(self) -> int:
        """Number of clips uploaded today."""
        return self._check_daily_limit()
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None