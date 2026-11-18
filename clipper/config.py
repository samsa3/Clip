from dataclasses import dataclass, field
import yaml
import sys
import argparse

@dataclass
class Config:
    buffer_seconds: int = 60
    segment_seconds: int = 5
    pre_roll: int = 10
    post_roll: int = 20
    threshold: float = 3.0
    sustained_min: int = 8
    fire_score: int = 55
    debounce_seconds: int = 45
    quality: str = "best"
    no_encode: bool = False
    output_dir: str = "clips"
    max_clips: int = 50
    reaction_lexicon: list[str] = field(default_factory=lambda: [
        "pog", "poggers", "letsgo", "clipit", "clip it", "lul", "kek",
        "kekw", "w", "insane", "clutch", "unreal", "pogu"
    ])

    @classmethod
    def load(cls, path: str = None) -> 'Config':
        config = cls()
        if path:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
                if data:
                    for key, value in data.items():
                        if hasattr(config, key):
                            setattr(config, key, value)
        return config
