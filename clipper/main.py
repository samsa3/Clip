import asyncio
import argparse
import sys
from clipper.config import Config
from clipper.url_resolver import resolve
from clipper.video import VideoBuffer
from clipper.detect import SpikeDetector

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Stream URL")
    parser.add_argument("--config", help="Config file path")
    args = parser.parse_args()

    config = Config.load(args.config)

    print(f"Resolving {args.url}...")
    stream_url, platform, channel = resolve(args.url)
    if not stream_url:
        print("Failed to resolve stream URL.")
        sys.exit(1)

    print(f"Platform: {platform}, Channel: {channel}")

    chat = None
    if platform == "twitch":
        from clipper.chat.twitch import TwitchChat
        chat = TwitchChat()
        print(f"Connecting to Twitch chat: {channel}")
        await chat.connect(channel)

    video = VideoBuffer(stream_url, config=config)
    print("Starting video pipeline...")
    await video.start()

    detector = SpikeDetector(
        threshold=config.threshold,
        sustained_min=config.sustained_min,
        fire_score=config.fire_score,
        debounce_seconds=config.debounce_seconds,
        lexicon=config.reaction_lexicon,
        on_spike=lambda info: print(f"SPIKE! score={info[\"score\"]:.1f} burst={info[\"burst\"]} sim={info[\"similarity\"]:.2f} emote={info[\"emote_density\"]:.2f} cue={info[\"cue_density\"]:.2f} phrase={info[\"top_phrase\"]!r}")
    )

    async def log_chat():
        if chat:
            async for msg in chat.messages():
                detector.on_message(msg)

    chat_task = asyncio.create_task(log_chat())

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        print("Stopping...")
        chat_task.cancel()
        if chat:
            await chat.close()
        await video.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
