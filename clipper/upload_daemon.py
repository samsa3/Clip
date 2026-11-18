"""Upload daemon entry point.

Runs InstagramUploader in a loop with configurable poll interval.
Handles graceful shutdown on SIGTERM/SIGINT.
"""
import argparse
import asyncio
import os
import signal
import sys
from clipper.config import Config
from clipper.upload import InstagramUploader

async def _run_daemon(config: Config):
    uploader = _build_uploader(config)
    
    uploader.login()
    
    poll_interval = config.instagram_poll_interval_seconds
    
    stop_event = asyncio.Event()
    
    def signal_handler():
        stop_event.set()
    
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
    
    try:
        while not stop_event.is_set():
            try:
                uploader.process_pending()
            except Exception as e:
                print(f"Upload cycle error: {e}")
            
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                continue
    finally:
        uploader.close()

def _build_uploader(config: Config) -> InstagramUploader:
    username = config.instagram_username or os.environ.get("IG_USERNAME", "")
    password = config.instagram_password or os.environ.get("IG_PASSWORD", "")
    return InstagramUploader(
        username=username,
        password=password,
        session_path=config.instagram_session_file,
        db_path=config.instagram_db_path,
        config={
            "daily_limit": 25,
            "caption_template": config.instagram_caption_template,
            "fallback_hashtags": config.instagram_fallback_hashtags,
            "max_hashtags": config.instagram_max_hashtags,
        }
    )

def main():
    parser = argparse.ArgumentParser(description="Instagram upload daemon")
    parser.add_argument("--login-only", action="store_true",
                        help="Perform initial login (handles 2FA) and exit")
    args = parser.parse_args()
    
    config = Config.load()
    
    uploader = _build_uploader(config)
    
    if args.login_only:
        uploader.login()
        print("Login successful. Session saved.")
        uploader.close()
        return
    
    asyncio.run(_run_daemon(config))

if __name__ == "__main__":
    main()