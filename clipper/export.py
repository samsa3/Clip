"""Clip exporter: segment list -> MP4 + metadata.json.

Runs ffmpeg concat in a thread executor so the asyncio loop is never
blocked. One export at a time; extra spikes queue up.
"""
import asyncio
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from clipper.video import Segment

class ClipExporter:
    def __init__(self, output_dir: str, buffer_dir: str = "buffer",
                 max_clips: int = 50, max_concurrency: int = 1):
        self.output_dir = output_dir
        self.buffer_dir = buffer_dir
        self.max_clips = max_clips
        self._executor = ThreadPoolExecutor(max_workers=max_concurrency)
        self._queue = asyncio.Queue()
        self._running = True
        self._count = 0
        os.makedirs(output_dir, exist_ok=True)

    def queue(self, spike_info: dict, segments: list[Segment]):
        self._queue.put_nowait((spike_info, segments))

    async def run(self):
        while self._running:
            try:
                spike_info, segments = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if not segments:
                continue
            await self._export(spike_info, segments)
            self.rotate()
            self._queue.task_done()

    async def _export(self, spike_info, segments):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._do_export, spike_info, segments)

    def _do_export(self, spike_info, segments):
        ts = datetime.fromtimestamp(spike_info["time"], tz=timezone.utc)
        stamp = ts.strftime("%Y%m%d_%H%M%S")
        self._count += 1
        name = f"clip_{stamp}_{self._count:03d}.mp4"
        out_path = os.path.join(self.output_dir, name)

        # Build concat list; skip segments missing on disk
        list_path = os.path.join(self.buffer_dir, f"_concat_{self._count:03d}.txt")
        paths = []
        for s in segments:
            if s.path and os.path.exists(s.path):
                paths.append(s.path)
        if not paths:
            return None
        with open(list_path, "w") as f:
            for p in paths:
                f.write(f"file '{os.path.abspath(p)}'\n")

        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
               "-i", list_path, "-c", "copy", out_path]
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
        try:
            os.remove(list_path)
        except OSError:
            pass
        if proc.returncode != 0:
            return None

        meta = {
            "file": out_path,
            "timestamp": spike_info["time"],
            "score": spike_info["score"],
            "burst": spike_info["burst"],
            "burst_ratio": spike_info["burst_ratio"],
            "sustained": spike_info["sustained"],
            "similarity": spike_info["similarity"],
            "emote_density": spike_info["emote_density"],
            "cue_density": spike_info["cue_density"],
            "top_phrase": spike_info["top_phrase"],
            "chat_sample": spike_info["chat_sample"],
            "segments": [os.path.basename(s.path) for s in segments],
            "duration": len(segments) * 5,
        }
        meta_path = os.path.join(self.output_dir, f"clip_{stamp}_{self._count:03d}.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        return out_path

    def rotate(self):
        """Drop oldest clips when over max_clips."""
        clips = sorted(f for f in os.listdir(self.output_dir) if f.endswith(".mp4"))
        while len(clips) > self.max_clips:
            oldest = clips.pop(0)
            for ext in (".mp4", ".json"):
                p = os.path.join(self.output_dir, oldest + ext)
                if os.path.exists(p):
                    os.remove(p)

    async def stop(self):
        self._running = False
        await self._queue.join()
        self._executor.shutdown(wait=True)
