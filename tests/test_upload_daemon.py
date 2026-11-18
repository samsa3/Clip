# tests/test_upload_daemon.py
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from clipper.upload_daemon import main

def test_daemon_runs_one_cycle():
    with patch("clipper.upload_daemon.InstagramUploader") as mock_uploader_cls:
        mock_uploader = MagicMock()
        mock_uploader_cls.return_value = mock_uploader
        mock_uploader.login = MagicMock()
        mock_uploader.process_pending = MagicMock(return_value=2)
        
        async def run_once():
            task = asyncio.create_task(main())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        asyncio.run(run_once())
        
        mock_uploader.login.assert_called_once()
        mock_uploader.process_pending.assert_called()