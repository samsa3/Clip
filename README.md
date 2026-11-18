# Live Stream Auto-Clipper

Watches a live stream (Twitch / YouTube / any streamlink source), keeps a
rolling ~60s video buffer, and cuts MP4 clips whenever chat activity spikes.

## How it works

```
stream URL -> streamlink -> ffmpeg segment muxer (12 x 5s .ts, wrap)
                                |
chat (IRC WS / polling) -> SpikeDetector (rolling windows + scoring)
                                |
                     spike? -> ClipExporter (concat remux -> MP4 + metadata.json)
```

**Detection signals** (per message, rolling windows):
- burst: messages in last 5s
- sustained: messages in last 30s
- baseline: moving median of non-zero 5s bursts over ~3 min
- similarity: fraction of 5s messages matching the most common phrase
- emote density + reaction cue lexicon (pog, letsgo, clipit, kekw, ...)

**Fire** when: `burst_ratio >= threshold` (3.0) AND `sustained >= 8` AND
`score >= 55` AND debounce (45s) elapsed. Raid guard: a dominant phrase
carried by <3 unique users in the burst window is treated as spam, not hype.

## Requirements

- Python 3.11+
- ffmpeg on PATH
- streamlink (pip)

This repo ships a verified `.venv` — use `.venv\Scripts\python`.

## Usage

```
.venv\Scripts\python -m clipper <stream_url> [--config config.yaml]
    [--threshold 3.0] [--pre-roll 10] [--post-roll 20] [--buffer 60]
    [--debounce 45] [--fire-score 55] [--quality best|720p|480p]
    [--no-encode] [--output-dir clips] [--max-clips 50]
```

Example:

```
.venv\Scripts\python -m clipper https://twitch.tv/xqc --pre-roll 15
```

Clips land in `clips/` as `clip_YYYYMMDD_HHMMSS_NNN.mp4` + a
`metadata.json` per clip (score, burst, similarity, top phrase, chat sample,
segments used, duration). The folder is capped at `max_clips` (oldest
removed). Ctrl+C stops everything and prints a summary (clip count +
duration).

## Config

All parameters are in `clipper/config.py` with defaults (see plan §7).
Supply a `config.yaml` to override any of them:

```yaml
buffer_seconds: 60
pre_roll: 10
post_roll: 20
threshold: 3.0
fire_score: 55
quality: best
no_encode: false
output_dir: clips
max_clips: 50
```

CLI flags override the YAML file, which overrides defaults.

## Tuning notes

- **Stream latency vs chat spike**: chat reacts ~5-15s after the event.
  `pre_roll` defaults to 10 (low-latency Twitch). Use `--pre-roll 30` for
  normal-latency streams.
- **Re-encode vs copy**: default re-encodes with libx264 ultrafast + short
  2s GOP so clips can start on any segment boundary. `--no-encode` uses
  `-c copy` (faster, cuts aligned to stream keyframes).
- **Small channels**: the baseline adapts down automatically; lower
  `--threshold 2.0` if it misses events.
- **Buffer dir churn**: `buffer/` holds ~12 x 5s .ts files (~200-500MB,
  capped by the segment wrap). Startup kills orphan ffmpeg processes
  writing into it.

## Testing

```
.venv\Scripts\python -m pytest tests/ -q
```

- `test_video.py` — segment ring capacity/wrap + window selection
- `test_chat.py` — IRC line parsing (tmi-sent-ts, display-name)
- `test_detect.py` — steady chat silent, engineered burst fires, debounce,
  raid guard, score computation
- `test_export.py` — real ffmpeg concat remux of testsrc segments -> valid
  MP4 + metadata

## Consent / ToS

This tool records publicly streamed content for personal clipping. Twitch
ToS restricts automated capture and redistribution; streamers may opt out
of clipping. Use responsibly and honor streamer requests. YouTube chat is
best-effort (polling, weaker timestamps) and isolated in
`clipper/chat/youtube.py`.
