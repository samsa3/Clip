import pytest
import time
from clipper.detect import SpikeDetector
from clipper.chat.base import ChatMessage

def make_detector(**kw):
    defaults = dict(threshold=3.0, sustained_min=8, fire_score=55,
                    debounce_seconds=45, lexicon=["pog", "lul", "kekw"],
                    now=time.time)
    defaults.update(kw)
    return SpikeDetector(**defaults)

def burst(n, start, users="u", text="pog pog pog", step=0.4):
    return [ChatMessage(timestamp=start + i * step, user=f"{users}{i%7}", text=text) for i in range(n)]

def test_steady_chat_does_not_fire():
    d = make_detector()
    t0 = time.time()
    # 1 msg every 3s for 90s -> steady, low
    msgs = [ChatMessage(timestamp=t0 + i * 3, user=f"u{i}", text="hello there friends") for i in range(30)]
    for m in msgs:
        d.on_message(m)
    assert not d.fired

def test_burst_fires():
    d = make_detector()
    t0 = time.time()
    # warm up: steady for 60s so baseline is low
    for i in range(20):
        d.on_message(ChatMessage(timestamp=t0 + i * 3, user=f"u{i}", text="normal chat talk"))
    # spike: 30 msgs in 5s from many users, all same emote phrase
    spike = burst(30, t0 + 60, users="spiker")
    for m in spike:
        d.on_message(m)
    assert d.fired, "expected spike to fire"

def test_debounce_prevents_immediate_refire():
    d = make_detector()
    t0 = time.time()
    for i in range(20):
        d.on_message(ChatMessage(timestamp=t0 + i * 3, user=f"u{i}", text="normal chat"))
    spike = burst(30, t0 + 60, users="spiker")
    for m in spike:
        d.on_message(m)
    assert d.fired
    # second spike 5s later must be suppressed (45s debounce)
    spike2 = burst(30, t0 + 65, users="spike2")
    fired_before = d.fire_count
    for m in spike2:
        d.on_message(m)
    assert d.fire_count == fired_before

def test_raid_guard_downgrades_low_unique_users():
    d = make_detector()
    t0 = time.time()
    for i in range(20):
        d.on_message(ChatMessage(timestamp=t0 + i * 3, user=f"u{i}", text="normal chat"))
    # 30 messages but from only 2 users -> raid-like, should not fire
    raid = [ChatMessage(timestamp=t0 + 60 + i * 0.4, user=f"raider{i%2}", text="pog pog pog") for i in range(30)]
    for m in raid:
        d.on_message(m)
    assert not d.fired

def test_score_computation():
    d = make_detector()
    t0 = time.time()
    for i in range(20):
        d.on_message(ChatMessage(timestamp=t0 + i * 3, user=f"u{i}", text="normal chat"))
    spike = burst(30, t0 + 60, users="spiker")
    for m in spike:
        d.on_message(m)
    # score should be high when spike present
    assert d.last_score is not None and d.last_score >= 55
