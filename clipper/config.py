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

    @classmethod
    def from_args(cls, argv=None) -> 'Config':
        parser = argparse.ArgumentParser(description="Live stream auto-clipper")
        parser.add_argument("url", help="Stream URL")
        parser.add_argument("--config", help="Config file path")
        parser.add_argument("--buffer", type=int, help="Buffer seconds")
        parser.add_argument("--segment", type=int, help="Segment seconds")
        parser.add_argument("--pre-roll", type=int, help="Pre-roll seconds")
        parser.add_argument("--post-roll", type=int, help="Post-roll seconds")
        parser.add_argument("--threshold", type=float, help="Burst ratio threshold")
        parser.add_argument("--sustained-min", type=int, help="Sustained window floor")
        parser.add_argument("--fire-score", type=int, help="Score threshold to fire")
        parser.add_argument("--debounce", type=int, help="Debounce seconds")
        parser.add_argument("--quality", choices=["best", "720p", "480p"], help="Stream quality")
        parser.add_argument("--no-encode", action="store_true", help="Copy without re-encode")
        parser.add_argument("--output-dir", help="Output directory")
        parser.add_argument("--max-clips", type=int, help="Max clips to keep")
        args = parser.parse_args(argv)

        config = cls.load(args.config)
        if args.buffer is not None:
            config.buffer_seconds = args.buffer
        if args.segment is not None:
            config.segment_seconds = args.segment
        if args.pre_roll is not None:
            config.pre_roll = args.pre_roll
        if args.post_roll is not None:
            config.post_roll = args.post_roll
        if args.threshold is not None:
            config.threshold = args.threshold
        if args.sustained_min is not None:
            config.sustained_min = args.sustained_min
        if args.fire_score is not None:
            config.fire_score = args.fire_score
        if args.debounce is not None:
            config.debounce_seconds = args.debounce
        if args.quality is not None:
            config.quality = args.quality
        if args.no_encode:
            config.no_encode = True
        if args.output_dir is not None:
            config.output_dir = args.output_dir
        if args.max_clips is not None:
            config.max_clips = args.max_clips
        return config, args.url
