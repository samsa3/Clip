"""Upload daemon entry point.

Runs InstagramUploader in a loop with configurable poll interval.
Handles graceful shutdown on SIGTERM/SIGINT.
"""
import asyncio
import signal
import sys
from clipper.config import Config
from clipper.upload import InstagramUploader

async def main():
    config = Config.load()
    
    uploader = InstagramUploader(
        username=config.instagram_username,
        password=config.instagram_password,
        session_path=config.instagram_session_file,
        db_path=config.instagram_db_path,
        config={
            "daily_limit": 25,
            "caption_template": config.instagram_caption_template,
            "fallback_hashtags": config.instagram_fallback_hashtags,
            "max_hashtags": config.instagram_max_hashtags,
        }
    )
    
    uploader.login()
    
    poll_interval = config.instagram_poll_interval_seconds
    
    stop_event = asyncio.Event()
    
    def signal_handler():
        stop_event.set()
    
    # Signal handling only works on Unix
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
            
            # Sleep with early exit on stop
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                continue
    finally:
        uploader.close()

if __name__ == "__main__":
    asyncio.run(main())