"""Entry point: live stream auto-clipper.

Wires the four async tasks together — video buffer, chat listener,
spike detector, clip exporter — and handles shutdown, orphan cleanup,
and a final summary line.
"""
import asyncio
import glob
import os
import signal
import sys
import time

from clipper.config import Config
from clipper.url_resolver import resolve
from clipper.video import VideoBuffer
from clipper.detect import SpikeDetector
from clipper.export import ClipExporter


def _orphan_cleanup(buffer_dir: str):
    """Kill any leftover ffmpeg writing into the buffer dir."""
    import subprocess
    try:
        out = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True
        ).stdout
    except Exception:
        return
    for line in out.splitlines():
        if "ffmpeg" in line and buffer_dir in line:
            pid = line.split()[1]
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass


async def _run_chat_with_reconnect(chat, channel, detector, on_connect):
    """Reconnect loop with exponential backoff; re-warm baseline after."""
    delay = 2.0
    while True:
        try:
            await chat.connect(channel)
            if on_connect:
                await on_connect()
            delay = 2.0
            async for msg in chat.messages():
                detector.on_message(msg)
        except asyncio.CancelledError:
            await chat.close()
            return
        except Exception as e:
            print(f"Chat error: {e}; reconnecting in {delay:.0f}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60.0)


async def main():
    config, url = Config.from_args()

    print(f"Resolving {url}...")
    stream_url, platform, channel = resolve(url)
    if not stream_url:
        print("Failed to resolve stream URL.")
        sys.exit(1)
    print(f"Platform: {platform}, Channel: {channel}")

    os.makedirs(config.output_dir, exist_ok=True)
    buffer_dir = "buffer"
    os.makedirs(buffer_dir, exist_ok=True)
    _orphan_cleanup(buffer_dir)

    chat = None
    if platform == "twitch":
        from clipper.chat.twitch import TwitchChat
        chat = TwitchChat()

    video = VideoBuffer(stream_url, config=config)
    print("Starting video pipeline...")
    await video.start()
    watch_task = asyncio.create_task(video.watch_segments())

    exporter = ClipExporter(
        output_dir=config.output_dir,
        buffer_dir=buffer_dir,
        max_clips=config.max_clips,
    )

    detector = SpikeDetector(
        threshold=config.threshold,
        sustained_min=config.sustained_min,
        fire_score=config.fire_score,
        debounce_seconds=config.debounce_seconds,
        lexicon=config.reaction_lexicon,
        on_spike=lambda info: (
            print(f"SPIKE! score={info['score']:.1f} burst={info['burst']} "
                  f"sim={info['similarity']:.2f} emote={info['emote_density']:.2f} "
                  f"cue={info['cue_density']:.2f} phrase={info['top_phrase']!r}"),
            exporter.queue(info, video.ring.select(info["time"])),
        ),
    )

    start_time = time.time()
    if chat:
        chat_task = asyncio.create_task(
            _run_chat_with_reconnect(chat, channel, detector, None))
    else:
        chat_task = asyncio.create_task(asyncio.sleep(0))

    export_task = asyncio.create_task(exporter.run())

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        print("Stopping...")
        chat_task.cancel()
        watch_task.cancel()
        export_task.cancel()
        if chat:
            await chat.close()
        await video.stop()
        await exporter.stop()
        elapsed = time.time() - start_time
        print(f"Done: {detector.fire_count} clips in {elapsed / 60:.1f} min")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
