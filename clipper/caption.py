"""Caption generation from clip metadata."""

import json
import re
from string import Formatter
from typing import Any


class SafeDict(dict):
    """Dictionary that returns empty string for missing keys during formatting."""
    
    def __missing__(self, key: str) -> str:
        return ""


def extract_hashtags_from_chat(chat_sample: str) -> list[str]:
    """Extract hashtags from chat sample.
    
    Looks for words starting with #. Returns lowercase, deduplicated tags.
    """
    if not chat_sample:
        return []
    
    tags = set()
    
    # Extract explicit hashtags only
    for match in re.finditer(r'#(\w+)', chat_sample):
        tags.add(match.group(1).lower())
    
    return list(tags)


def generate_caption(
    meta_path: str,
    template: str,
    fallback_hashtags: list[str],
    max_hashtags: int
) -> str:
    """Generate Instagram caption from clip metadata.
    
    Args:
        meta_path: Path to the clip's metadata JSON file
        template: Template string with placeholders like {top_phrase}, {score}, {chat_sample}, {hashtags}
        fallback_hashtags: List of hashtag strings (without #) to use when chat has no tags
        max_hashtags: Maximum number of hashtags to include
        
    Returns:
        Formatted caption string
    """
    with open(meta_path, 'r') as f:
        metadata = json.load(f)
    
    # Extract hashtags from chat_sample
    chat_sample = metadata.get('chat_sample', '')
    chat_tags = extract_hashtags_from_chat(chat_sample)
    
    # Use chat tags if available, otherwise fallback
    if chat_tags:
        tags_to_use = chat_tags
    else:
        tags_to_use = fallback_hashtags
    
    # Limit and format hashtags
    hashtags = " ".join(f"#{tag}" for tag in tags_to_use[:max_hashtags])
    
    # Prepare format dict with metadata + hashtags
    format_dict = SafeDict(metadata)
    format_dict['hashtags'] = hashtags
    
    # Format template safely (missing keys become empty string)
    return template.format_map(format_dict)