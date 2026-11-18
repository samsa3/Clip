# tests/test_export_db_hook.py
import tempfile
import os
from unittest.mock import patch
from clipper.export import ClipExporter
from clipper.db import init_db, get_pending
from clipper.video import Segment

def test_exporter_registers_clip_in_db():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = f"{tmp}/clips"
        buffer_dir = f"{tmp}/buffer"
        db_path = f"{tmp}/clips.db"
        os.makedirs(output_dir)
        os.makedirs(buffer_dir)
        
        conn = init_db(db_path)
        
        exporter = ClipExporter(output_dir=output_dir, buffer_dir=buffer_dir, db_path=db_path)
        
        segments = [
            Segment(1, 1000.0, 1005.0, f"{buffer_dir}/seg_001.ts"),
            Segment(2, 1005.0, 1010.0, f"{buffer_dir}/seg_002.ts"),
        ]
        for s in segments:
            with open(s.path, "wb") as f:
                f.write(b"fake")
        
        spike_info = {
            "time": 1007.0,
            "score": 60,
            "burst": 20,
            "burst_ratio": 4.0,
            "sustained": 15,
            "similarity": 0.8,
            "emote_density": 0.3,
            "cue_density": 0.2,
            "top_phrase": "poggers",
            "chat_sample": "poggers letsgo",
        }
        
        import subprocess
        original_run = subprocess.run
        def mock_run(cmd, *args, **kwargs):
            if "concat" in cmd:
                out_path = cmd[cmd.index("-i") + 2] if "-i" in cmd else None
                if out_path and out_path.endswith(".mp4"):
                    with open(out_path, "wb") as f:
                        f.write(b"fake mp4")
                return subprocess.CompletedProcess(cmd, 0, b"", b"")
            return original_run(cmd, *args, **kwargs)
        
        with patch("subprocess.run", side_effect=mock_run):
            exporter._do_export(spike_info, segments)
        
        pending = get_pending(conn)
        assert len(pending) == 1
        assert pending[0].file_path.endswith(".mp4")
        assert pending[0].meta_path.endswith(".json")
        
        conn.close()