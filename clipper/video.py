import asyncio
import subprocess
import os
from dataclasses import dataclass
from collections import deque

@dataclass
class Segment:
    segment_id: int
    start_wall: float
    end_wall: float
    path: str

class SegmentRing:
    def __init__(self, buffer_seconds=60, segment_seconds=5, pre_roll=10, post_roll=20):
        self.capacity = buffer_seconds // segment_seconds
        self.segment_seconds = segment_seconds
        self.pre_roll = pre_roll
        self.post_roll = post_roll
        self.entries = deque(maxlen=self.capacity)

    def add(self, segment_id, start_wall, end_wall, path=""):
        self.entries.append(Segment(segment_id, start_wall, end_wall, path))

    def select(self, spike_wall):
        # [spike - pre_roll, spike + post_roll]
        start_t = spike_wall - self.pre_roll
        end_t = spike_wall + self.post_roll
        
        selected = []
        for s in self.entries:
            # Overlap: segment end > start_t AND segment start < end_t
            if s.end_wall > start_t and s.start_wall < end_t:
                selected.append(s)
        return selected

class VideoBuffer:
    def __init__(self, stream_url, buffer_dir="buffer", config=None):
        self.stream_url = stream_url
        self.buffer_dir = buffer_dir
        os.makedirs(buffer_dir, exist_ok=True)
        self.proc = None
        # Ring setup from config or defaults
        self.ring = SegmentRing(
            buffer_seconds=config.buffer_seconds if config else 60,
            segment_seconds=config.segment_seconds if config else 5,
            pre_roll=config.pre_roll if config else 10,
            post_roll=config.post_roll if config else 20
        )

    async def start(self):
        cmd = [
            "ffmpeg", "-i", self.stream_url,
            "-c", "copy",
            "-f", "segment", "-segment_time", str(self.ring.segment_seconds),
            "-segment_wrap", str(self.ring.capacity),
            "-reset_timestamps", "1",
            os.path.join(self.buffer_dir, "seg_%03d.ts")
        ]
        self.proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )

    async def stop(self):
        if self.proc:
            try:
                if self.proc.returncode is None:
                    self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=3.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    self.proc.kill()
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                pass

