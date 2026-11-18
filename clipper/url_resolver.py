import streamlink
import logging

logger = logging.getLogger(__name__)

def resolve(url: str):
    session = streamlink.Streamlink()
    try:
        streams = session.streams(url)
        if not streams:
            return None, None, None
        
        # Determine platform and channel
        platform = "unknown"
        channel = "unknown"
        if "twitch.tv" in url:
            platform = "twitch"
            channel = url.split("/")[-1].split("?")[0]
        elif "youtube.com" in url or "youtu.be" in url:
            platform = "youtube"
            channel = "youtube_stream"
        
        # Pick best stream
        stream_url = None
        if "best" in streams:
            stream_url = streams["best"].url
        elif streams:
            stream_url = list(streams.values())[0].url
            
        return stream_url, platform, channel
    except Exception as e:
        logger.error(f"Failed to resolve {url}: {e}")
        return None, None, None
