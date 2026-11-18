# tests/test_video_check.py
from clipper.video_check import validate_reels_spec, VideoInfo
import subprocess, tempfile, os

def make_test_video(path, duration=10, width=1920, height=1080):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=30,format=yuv420p",
           "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}", "-c:v", "libx264", "-profile:v", "high",
           "-c:a", "aac", "-shortest", path]
    subprocess.run(cmd, check=True, capture_output=True)

def test_valid_reels_video_passes():
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        path = f.name
    try:
        make_test_video(path, duration=30, width=1920, height=1080)
        ok, err = validate_reels_spec(path)
        assert ok is True
        assert err == ""
    finally:
        os.unlink(path)

def test_too_long_fails():
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        path = f.name
    try:
        make_test_video(path, duration=90, width=1920, height=1080)
        ok, err = validate_reels_spec(path)
        assert ok is False
        assert "duration" in err.lower() or "60" in err
    finally:
        os.unlink(path)

def test_no_audio_fails():
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        path = f.name
    try:
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=10:size=1920x1080:rate=30,format=yuv420p",
                       "-c:v", "libx264", "-profile:v", "high", "-an", path], check=True, capture_output=True)
        ok, err = validate_reels_spec(path)
        assert ok is False
        assert "audio" in err.lower()
    finally:
        os.unlink(path)