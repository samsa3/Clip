import pytest
from clipper.video import SegmentRing, VideoBuffer
import asyncio
import os
import shutil

@pytest.mark.asyncio
async def test_buffer_creation():
    if os.path.exists("buffer_test"):
        shutil.rmtree("buffer_test")
    buffer = VideoBuffer("invalid_url", buffer_dir="buffer_test")
    await buffer.start()
    await asyncio.sleep(1)
    assert buffer.proc is not None
    await buffer.stop()
    if os.path.exists("buffer_test"):
        shutil.rmtree("buffer_test")

def test_ring_capacity_and_wrap():
    ring = SegmentRing(segment_seconds=5)
    for i in range(14):
        ring.add(i, start_wall=i * 5, end_wall=i * 5 + 5)
    assert len(ring.entries) == 12
    assert ring.entries[0].segment_id == 2

def test_ring_selects_covering_segments():
    ring = SegmentRing(segment_seconds=5, pre_roll=10, post_roll=20)
    for i in range(12):
        ring.add(i, start_wall=i * 5, end_wall=i * 5 + 5)
    selected = ring.select(spike_wall=50)
    assert selected[0].segment_id == 8
    assert selected[-1].segment_id == 11

def test_ring_empty():
    ring = SegmentRing(segment_seconds=5, pre_roll=10, post_roll=20)
    assert ring.select(spike_wall=100) == []
