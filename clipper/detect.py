"""Spike detection: rolling windows + scoring over chat messages.

Pure module (no I/O) — unit-testable with synthetic message streams.
"""
import re
import time
from collections import deque
from statistics import median

from clipper.chat.base import ChatMessage

BURST_WINDOW = 5.0
SUSTAINED_WINDOW = 30.0
BASELINE_WINDOW = 180.0  # ~3 min
RAID_MIN_UNIQUE_USERS = 3
RAID_SIMILARITY = 0.7

_WORD_RE = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


def _is_emote_heavy(text: str, lexicon: set) -> bool:
    """A message is emote-heavy when it is short and made of emote-like words."""
    words = text.split()
    if not words or len(words) > 4:
        return False
    lowered = {w.lower() for w in words}
    for w in lowered:
        if w in lexicon:
            return True
    # CamelCase-ish tokens (PepeLaugh, HypeTrain) or short CAPS words
    return all(_looks_like_emote(w) for w in words)


def _looks_like_emote(w: str) -> bool:
    if not w:
        return False
    if any(c in w for c in " !?.," ) or len(w) < 2:
        return False
    if w.islower():
        return False
    return w[0].isupper() or w.isupper()


class SpikeDetector:
    def __init__(self, threshold=3.0, sustained_min=8, fire_score=55,
                 debounce_seconds=45, lexicon=None, now=time.time,
                 on_spike=None):
        self.threshold = threshold
        self.sustained_min = sustained_min
        self.fire_score = fire_score
        self.debounce_seconds = debounce_seconds
        self.lexicon = set((lexicon or ["pog", "poggers", "letsgo", "clipit",
                                        "clip it", "lul", "kek", "kekw", "w",
                                        "insane", "clutch", "unreal", "pogu"]))
        self.now = now
        self.on_spike = on_spike  # optional callback(spike_info dict)

        self._msgs = deque()          # (ts, user, text) for rolling windows
        self._burst_samples = deque() # (ts, burst) sampled per 5s bucket
        self._last_sample = 0.0
        self.last_fire_time = None
        self.last_score = None
        self.fired = False
        self.fire_count = 0

    # -- helpers ---------------------------------------------------------
    def _prune(self, t: float):
        while self._msgs and self._msgs[0][0] < t - BASELINE_WINDOW:
            self._msgs.popleft()
        while self._burst_samples and self._burst_samples[0][0] < t - BASELINE_WINDOW:
            self._burst_samples.popleft()

    def _in_window(self, t: float, window: float):
        return [m for m in self._msgs if m[0] >= t - window]

    def _baseline(self):
        samples = [b for _, b in self._burst_samples if b > 0]
        if not samples:
            return 0.0
        return float(median(samples))

    # -- scoring ---------------------------------------------------------
    def _signals(self, t: float, recent):
        burst = len(recent)
        burst_ratio = burst / max(self._baseline(), 1.0)

        # similarity: fraction of burst messages matching most common phrase
        phrases = {}
        for _, _, text in recent:
            phrases[_normalize(text)] = phrases.get(_normalize(text), 0) + 1
        similarity = (max(phrases.values()) / burst) if burst else 0.0
        top_phrase = max(phrases, key=phrases.get) if phrases else ""

        emote = sum(1 for _, _, text in recent if _is_emote_heavy(text, self.lexicon))
        emote_density = emote / burst if burst else 0.0

        cues = 0
        for _, _, text in recent:
            low = " " + text.lower() + " "
            if any((" " + c in low) or (low.find(c) != -1 and c != "w")
                   for c in self.lexicon):
                cues += 1
        cue_density = cues / burst if burst else 0.0

        score = 100 * (0.50 * min(burst_ratio / self.threshold, 1.0)
                       + 0.20 * similarity
                       + 0.20 * emote_density
                       + 0.10 * cue_density)
        return burst, burst_ratio, similarity, emote_density, cue_density, score, top_phrase

    # -- main entry ------------------------------------------------------
    def on_message(self, msg: ChatMessage):
        t = msg.timestamp
        self._prune(t)
        self._msgs.append((t, msg.user, msg.text))

        # sample burst per 5s bucket for the baseline
        bucket = int(t / BURST_WINDOW)
        if self._last_sample != bucket or not self._burst_samples:
            self._last_sample = bucket
            burst_now = len(self._in_window(t, BURST_WINDOW))
            self._burst_samples.append((t, burst_now))

        recent = self._in_window(t, BURST_WINDOW)
        sustained = self._in_window(t, SUSTAINED_WINDOW)
        (burst, burst_ratio, similarity, emote_density,
         cue_density, score, top_phrase) = self._signals(t, recent)
        self.last_score = score

        if burst_ratio < self.threshold:
            return None
        if len(sustained) < self.sustained_min:
            return None
        if score < self.fire_score:
            return None
        # raid guard (plan §5): high similarity but <3 unique users -> spam
        # raid, not hype. Check the dominant phrase in the 5s burst window:
        # if it has many copies from very few users, it's a spam bot.
        phrase_users_5s: dict[str, set] = {}
        for _, u, text in recent:
            phrase_users_5s.setdefault(_normalize(text), set()).add(u)
        if phrase_users_5s:
            dom_phrase_5s = max(phrase_users_5s, key=lambda p: len(phrase_users_5s[p]))
            n_unique = len(phrase_users_5s[dom_phrase_5s])
            n_occur = sum(1 for _, _, text in recent if _normalize(text) == dom_phrase_5s)
            if n_occur >= 3 and n_unique < RAID_MIN_UNIQUE_USERS:
                return None
        # debounce: one hype moment = one clip
        if self.last_fire_time is not None and (t - self.last_fire_time) < self.debounce_seconds:
            return None

        self.last_fire_time = t
        self.fired = True
        self.fire_count += 1
        info = {
            "time": t,
            "score": score,
            "burst": burst,
            "burst_ratio": burst_ratio,
            "sustained": len(sustained),
            "similarity": similarity,
            "emote_density": emote_density,
            "cue_density": cue_density,
            "top_phrase": top_phrase,
            "chat_sample": [(u, txt) for _, u, txt in recent[-20:]],
        }
        if self.on_spike:
            self.on_spike(info)
        return info
