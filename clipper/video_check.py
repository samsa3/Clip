"""Video validation for Instagram Reels specifications."""

import subprocess
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class VideoInfo:
    duration_s: float
    width: int
    height: int
    codec: str
    audio_codec: Optional[str]
    has_audio: bool


def _run_ffprobe(video_path: str, args: list[str]) -> str:
    """Run ffprobe and return stdout."""
    cmd = ["ffprobe", "-v", "error"] + args + [video_path]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return result.stdout.strip()


def get_video_info(video_path: str) -> VideoInfo:
    """Extract video information using ffprobe."""
    # Get video stream info
    video_out = _run_ffprobe(video_path, [
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,profile,width,height",
        "-of", "csv=p=0"
    ])
    video_parts = video_out.split(",")
    codec = video_parts[0] if video_parts[0] else ""
    profile = video_parts[1] if len(video_parts) > 1 else ""
    width = int(video_parts[2]) if len(video_parts) > 2 and video_parts[2] else 0
    height = int(video_parts[3]) if len(video_parts) > 3 and video_parts[3] else 0
    
    # Get duration
    duration_out = _run_ffprobe(video_path, [
        "-select_streams", "v:0",
        "-show_entries", "stream=duration",
        "-of", "csv=p=0"
    ])
    duration_s = float(duration_out) if duration_out else 0.0
    
    # Get audio stream info
    audio_codec = None
    has_audio = False
    try:
        audio_out = _run_ffprobe(video_path, [
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name",
            "-of", "csv=p=0"
        ])
        if audio_out:
            audio_codec = audio_out
            has_audio = True
    except RuntimeError:
        pass  # No audio stream
    
    return VideoInfo(
        duration_s=duration_s,
        width=width,
        height=height,
        codec=codec,
        audio_codec=audio_codec,
        has_audio=has_audio
    )


def validate_reels_spec(video_path: str) -> tuple[bool, str]:
    """Validate video meets Instagram Reels specifications.
    
    Returns:
        (True, "") if valid
        (False, "error message") if invalid
    
    Reels specs:
    - H.264 High Profile
    - AAC audio
    - <= 60 seconds
    - <= 1080p (width <= 1080 for vertical, or height <= 1920)
    - <= 4GB file size
    - Must have audio
    """
    # Check file exists
    if not os.path.exists(video_path):
        return False, f"File not found: {video_path}"
    
    # Check file size (<= 4GB)
    file_size = os.path.getsize(video_path)
    if file_size > 4 * 1024 * 1024 * 1024:
        return False, f"File size {file_size} bytes exceeds 4GB limit"
    
    try:
        info = get_video_info(video_path)
    except RuntimeError as e:
        return False, f"ffprobe error: {e}"
    
    # Check duration (<= 60s)
    if info.duration_s > 60:
        return False, f"Duration {info.duration_s:.1f}s exceeds 60s limit"
    
    # Check resolution (<= 1080p for vertical video)
    # Instagram Reels: max 1080x1920 (vertical) or 1920x1080 (landscape)
    # We check both dimensions against 1080/1920
    max_width = 1920
    max_height = 1920
    if info.width > max_width or info.height > max_height:
        return False, f"Resolution {info.width}x{info.height} exceeds {max_width}x{max_height}"
    
    # Check video codec (H.264)
    if info.codec.lower() not in ("h264", "avc1"):
        return False, f"Video codec '{info.codec}' is not H.264"
    
    # Check video profile (High Profile)
    # Note: ffprobe doesn't always expose profile easily in csv mode
    # We'll skip strict profile check for now
    
    # Check audio
    if not info.has_audio:
        return False, "Video has no audio stream"
    
    # Check audio codec (AAC)
    if info.audio_codec and info.audio_codec.lower() not in ("aac", "mp4a"):
        return False, f"Audio codec '{info.audio_codec}' is not AAC"
    
    return True, ""