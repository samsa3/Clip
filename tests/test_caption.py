# tests/test_caption.py
import tempfile
import json
from clipper.caption import generate_caption

def test_generate_caption_from_metadata():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "top_phrase": "poggers",
            "score": 72.5,
            "chat_sample": "poggers letsgo clipit",
            "timestamp": 1705324222.0
        }, f)
        meta_path = f.name
    
    template = "{top_phrase} 🔥 score: {score:.0f} | {chat_sample}\n\n{hashtags}"
    fallback = ["twitch", "clips", "gaming", "reels", "viral"]
    
    caption = generate_caption(meta_path, template, fallback, max_hashtags=30)
    
    assert "poggers 🔥 score: 72" in caption
    assert "letsgo" in caption or "clipit" in caption
    assert "#twitch" in caption or "#clips" in caption
    assert caption.count("#") <= 30

def test_fallback_hashtags_when_no_chat_tags():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "top_phrase": "insane play",
            "score": 88.0,
            "chat_sample": "wow amazing",
            "timestamp": 1705324222.0
        }, f)
        meta_path = f.name
    
    template = "{top_phrase} 🔥 score: {score:.0f} | {chat_sample}\n\n{hashtags}"
    fallback = ["twitch", "clips", "gaming"]
    
    caption = generate_caption(meta_path, template, fallback, max_hashtags=10)
    
    assert "#twitch" in caption
    assert "#clips" in caption
    assert "#gaming" in caption

def test_missing_keys_render_empty():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"top_phrase": "test"}, f)
        meta_path = f.name
    
    template = "{top_phrase} | {missing_key} | {chat_sample}"
    caption = generate_caption(meta_path, template, [], 10)
    
    assert "test |  | " in caption