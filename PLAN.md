# Live Stream Auto-Clipper — Detailed Plan

## 1. Goal

A program where the user supplies a live stream URL (Twitch / YouTube / Kick /
any streamlink-supported source) and it:

1. Watches the live chat for engagement spikes (message rate, emote density,
   message similarity).
2. Keeps a rolling circular buffer of the last N seconds of video+audio.
3. When a spike is detected, remuxes the buffered window into an MP4 clip and
   saves it to the output folder.
4. Keeps running for the whole stream, producing clips as events fire.

Output: `clips/clip_YYYYMMDD_HHMMSS_<channel>.mp4` + a `metadata.json` per
clip (score, top emotes, chat sample).

## 2. Architecture

Three independent async tasks in one asyncio loop, coordinated via queues:

- video_task — owns ffmpeg circular buffer (streamlink -> ffmpeg)
- chat_task — platform chat plugin, emits MessageEvents
- detector_task — rolling windows + scoring, emits SpikeEvents
- exporter_task — on spike: remux buffered segments -> MP4 + metadata

Pipeline:
stream link -> URL resolver (streamlink) -> rolling video buffer (ffmpeg
segment muxer, wrap ~12 x 5s) + chat listener -> spike detector -> clip
exporter -> clips/*.mp4

## 3. Video pipeline (rolling buffer)

OBS-style replay buffer using ffmpeg segment muxer with wrap-around:

    streamlink <url> <quality> -O - | ffmpeg -i pipe:0 \
      -c:v libx264 -preset ultrafast -crf 22 -g 2 -keyint_min 2 -sc_threshold 0 \
      -c:a aac \
      -f segment -segment_time 5 -segment_wrap 12 -reset_timestamps 1 \
      -segment_format mpegts buffer/seg_%03d.ts

- 5s x 12 segments = ~60s rolling window (config BUFFER_S).
- Short forced GOP (2s) so a clip can start on any segment boundary with
  minimal quality ramp. --no-encode falls back to -c copy with cuts
  aligned to the stream's native keyframes.
- A Python ring holds (segment_id, wall_clock_start, end) for the last 12
  segments; on spike at time T the exporter picks all segments covering
  [T - PRE_ROLL, T + POST_ROLL] (defaults 10s pre / 20s post).
- Post-roll: wait until the needed segments are fully written, then remux:
  ffmpeg -f concat -safe 0 -i list.txt -c copy clips/clip_xxx.mp4
  (lossless, fast; run in a thread, one export at a time, rest queued).

Edge cases: reconnect -> restart ffmpeg, invalidate ring, mark gap in
metadata; stream end -> flush and exit cleanly; disk capped by the 12-segment
buffer (~200-500MB); max_clips rotation for the clips/ folder.

## 4. Chat listener (platform plugins)

One interface: ChatSource with connect(channel), messages() async iterator
(ts, user, text), close().

- Twitch (primary, zero-auth): read-only IRC over WebSocket
  (wss://irc.chat.twitch.tv:443, nick justinfan<rand>), CAP REQ
  :twitch.tv/tags, JOIN #channel. Use @tmi-sent-ts (real send time) for
  clock alignment. Exponential-backoff reconnect; on reconnect re-warm the
  baseline ~30s before allowing clips.
- YouTube (secondary, best-effort): poll the live-chat continuation endpoint
  (~2s cadence); publishedAtTimeText per entry. Weakest timestamp
  precision; documented.
- Kick/others: same plugin interface; any source streamlink can play gets
  the video pipeline for free — chat is what determines clip-ability.

## 5. Spike detection (core brain)

Signals (per message arrival, rolling windows):

- burst: messages in last 5s
- sustained: messages in last 30s
- baseline: moving median of non-zero bursts over ~3 min (adapts to channel
  size)
- emote_density: fraction of messages that are emote-only/emote-heavy
- similarity: fraction of last-5s messages matching the most common
  normalized phrase/emote set (many people saying the same thing)
- reaction_cues: small lexicon (pog, poggers, letsgo, clipit, kekw, lul,
  w, insane, clutch, unreal, ...)

Score = 100 * (0.50*min(burst/max(baseline,1)/THRESH_MAX,1)
              + 0.20*similarity + 0.20*emote_density + 0.10*cues)

Fire when: burst_ratio >= threshold (default 3.0), sustained >= sustained_min
(8 msgs/30s floor), score >= fire_score (55), and debounce elapsed (45s —
one hype moment = one clip). Raid guard: similarity high but <3 unique
users -> downgrade (likely spam raid, not hype).

Why heuristics, not ML/LLM, in the hot path: chat velocity + emote +
similarity is the proven explainable core used by commercial clippers;
fast and free. Optional v2: LLM captioner writes title/tags for fired
clips, post-hoc, never in the trigger path.

Clock alignment: chat tmi-sent-ts is real time; video ring uses wall-clock.
Stream latency means the highlight happens before the chat spike — 10s
pre-roll covers low-latency Twitch; use --pre-roll 30 for normal latency.

## 6. Program structure

Single repo, Python 3.11+, asyncio:

    clipper/
    ├── main.py          # CLI entry
    ├── config.py        # dataclass + YAML/CLI merge
    ├── url_resolver.py  # streamlink: url -> (stream_url, platform, channel)
    ├── video.py         # VideoBuffer: ffmpeg process, segment ring, stop()
    ├── chat/
    │   ├── base.py      # ChatSource, ChatMessage
    │   ├── twitch.py    # IRC websocket reader
    │   └── youtube.py   # polling reader
    ├── detect.py        # windows + scoring (pure, unit-testable)
    ├── export.py        # segment list -> MP4 + metadata
    └── requirements.txt # streamlink, websockets, aiohttp, pyyaml

External deps on PATH: ffmpeg, streamlink.

CLI:

    python -m clipper <stream_url> [--config config.yaml]
        [--threshold 3.0] [--pre-roll 10] [--post-roll 20] [--buffer 60]
        [--debounce 45] [--fire-score 55] [--quality best|720p|480p]
        [--no-encode] [--output-dir clips] [--max-clips 50]

Shutdown: Ctrl+C or stream end -> stop chat, flush pending exports, kill
ffmpeg (SIGTERM, 3s wait, SIGKILL), summary line (N clips, X min). Startup
orphan guard: kill leftover ffmpeg writing into the buffer dir.

## 7. Config defaults (config.yaml)

    buffer_seconds: 60
    segment_seconds: 5
    pre_roll: 10
    post_roll: 20
    threshold: 3.0
    sustained_min: 8
    fire_score: 55
    debounce_seconds: 45
    quality: best
    no_encode: false
    output_dir: clips
    max_clips: 50
    reaction_lexicon: [pog, poggers, letsgo, clipit, clip it, lul, kek,
                       kekw, w, insane, clutch, unreal, pogu]

## 8. Implementation order

1. Scaffold + video pipeline alone: URL resolve, circular buffer running;
   verify segments wrap and ring bookkeeping. Milestone: watch the buffer
   dir churn for 5 min.
2. Twitch chat listener: anonymous connect, print messages with tmi-sent-ts.
   Milestone: stable 30 min on a busy channel incl. one forced reconnect.
3. Detector: pure module, unit-tested with synthetic message bursts (fires
   on engineered spikes, silent on steady chat); wire into app. Milestone:
   live scores logged on a real channel, sanity-check 3-4 triggers.
4. Exporter: segment remux + metadata. Milestone: first real MP4 from a live
   spike, plays anywhere.
5. Hardening: reconnects, gaps, Ctrl+C summary, orphan cleanup, max_clips
   rotation, README (ffmpeg/streamlink install, consent/ToS note).
6. Optional v2 (out of scope): YouTube chat, LLM captioner, audio-RMS
   fusion, auto-post to socials.

Each phase ends with a manual smoke run against a real live stream.

## 9. Risks

- Stream latency vs chat spike -> tunable pre_roll, documented defaults.
- Twitch IRC changes / anonymous blocks -> read-only IRC long-stable;
  fallback is a free user-created OAuth app.
- CPU on 1080p60 re-encode -> ultrafast preset, 720p or --no-encode,
  optional NVENC flag later.
- False positives (raids/spam) -> sustained floor + uniqueness check.
- False negatives (small channels) -> median baseline adapts down,
  --threshold 2.0 available.
- Segment drift (CDN loops) -> gap flag in metadata, documented limitation.
- YouTube scraping fragility -> isolated plugin, best-effort, documented.

## 10. Non-goals (v1)

No social auto-posting, no audio-energy detection, no LLM in trigger path,
no multi-channel in one process, no GUI.

## 11. Environment & dependencies — verified on this machine (2026-11-18)

| Dependency | Status |
|---|---|
| Python 3.14.9 | present |
| ffmpeg 9.0.1 | present on PATH (C:\Users\Sam\AppData\Local\hermes\tools\ffmpeg-9.0.1-win32-x64\bin) |
| streamlink 8.6.3 | installed into project venv `Clip\.venv` |
| pyyaml, websockets, aiohttp | installed into `Clip\.venv` |

All dependencies are installed — nothing left for the user to install.
Run everything with `Clip\.venv\Scripts\python`. (Note: the venv initially
had no pip; it was bootstrapped with `python -m ensurepip`.)

Mechanism pre-tested and working:
- Circular segment buffer: 70s of synthetic video -> exactly 12 x 5s .ts
  segments with wrap-around (11-12 files on disk at any time).
- Clip remux: concat of 3 buffered segments -> valid 15.0s MP4
  (ffprobe confirmed `format_name=mov,mp4,...`, duration 15.008s).
- URL resolver: `streamlink.resolve_url` succeeds for twitch.tv and
  kick.com URLs; youtube.com watch-URLs need the plugin's live-format
  branch (handled inside url_resolver.py — streamlink picks the
  `hls:live` format for live watch URLs).

No third-party service/API keys are required for v1 (Twitch chat is
anonymous read-only; streamlink needs no accounts).
