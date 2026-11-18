import asyncio
import argparse
import sys
from clipper.config import Config
from clipper.url_resolver import resolve
from clipper.video import VideoBuffer

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
    
    video = VideoBuffer(stream_url, config=config)
    print("Starting video pipeline...")
    await video.start()
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        print("Stopping...")
        await video.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
