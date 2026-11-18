import pytest
from clipper.export import ClipExporter
from clipper.video import Segment
import os
import shutil
import time

def test_exporter_writes_mp4_and_metadata(tmp_path):
    out_dir = str(tmp_path / "clips")
    buf_dir = str(tmp_path / "buffer")
    os.makedirs(buf_dir, exist_ok=True)

    # Create 3 real 5s testsrc .ts segments with ffmpeg
    import subprocess
    for i in range(3):
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=5:size=128x72:rate=10",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             os.path.join(buf_dir, f"seg_{i:03d}.ts")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        assert r.returncode == 0
    
    exp = ClipExporter(output_dir=out_dir, buffer_dir=buf_dir, max_clips=5)
    
    segments = [
        Segment(segment_id=0, start_wall=0, end_wall=5, path=os.path.join(buf_dir, "seg_000.ts")),
        Segment(segment_id=1, start_wall=5, end_wall=10, path=os.path.join(buf_dir, "seg_001.ts")),
        Segment(segment_id=2, start_wall=10, end_wall=15, path=os.path.join(buf_dir, "seg_002.ts")),
    ]
    spike = {
        "time": time.time(), "score": 75.0, "burst": 20, "burst_ratio": 5.0,
        "sustained": 30, "similarity": 0.5, "emote_density": 0.4,
        "cue_density": 0.1, "top_phrase": "pog", "chat_sample": [],
    }
    
    # Run the export synchronously (bypassing asyncio queue)
    result = exp._do_export(spike, segments)
    assert result is not None
    assert os.path.exists(result)
    assert result.endswith(".mp4")
    
    # Check metadata
    meta_files = [f for f in os.listdir(out_dir) if f.endswith(".json")]
    assert len(meta_files) == 1
    import json
    with open(os.path.join(out_dir, meta_files[0])) as f:
        meta = json.load(f)
    assert meta["score"] == 75.0
    assert meta["top_phrase"] == "pog"
    assert len(meta["segments"]) == 3
