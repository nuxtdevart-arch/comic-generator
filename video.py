"""Video rendering: ffmpeg per-scene + ASS subtitles + concat.

Pattern mirrors tts.py — standalone module imported by generate_comic.
"""
import logging
import hashlib
from pathlib import Path
from typing import Optional

log = logging.getLogger("comic.video")


QUALITY_PRESETS: dict[str, dict] = {
    "draft": {"res": (1280, 720),  "fps": 24, "crf": 28, "preset": "ultrafast"},
    "final": {"res": (1920, 1080), "fps": 30, "crf": 18, "preset": "medium"},
}


def _fmt_ass_time(seconds: float) -> str:
    """Format seconds as ASS time: H:MM:SS.cc (centiseconds, not ms)."""
    total_cs = int(round(seconds * 100))
    h = total_cs // 360000
    m = (total_cs // 6000) % 60
    s = (total_cs // 100) % 60
    cs = total_cs % 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _hex_to_ass_color(hex_str: str) -> str:
    """Convert #RRGGBB to ASS &H00BBGGRR (BGR + alpha)."""
    h = hex_str.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: {hex_str}")
    try:
        r, g, b = h[0:2], h[2:4], h[4:6]
        # ASS is &H AABBGGRR, we use 00 for alpha
        return f"&H00{b}{g}{r}".upper()
    except Exception:
        raise ValueError(f"Invalid hex color: {hex_str}")


def compute_video_hash(
    img_path: Path,
    audio_path: Optional[Path],
    ass_block: str,
    quality: str,
    fps: int,
    resolution: tuple[int, int],
) -> str:
    """sha256 of content bytes + render parameters. Stable across runs."""
    h = hashlib.sha256()
    h.update(Path(img_path).read_bytes())
    if audio_path is not None and Path(audio_path).exists():
        h.update(Path(audio_path).read_bytes())
    else:
        h.update(b"<no-audio>")
    h.update(ass_block.encode("utf-8"))
    h.update(quality.encode("utf-8"))
    h.update(f"{fps}|{resolution[0]}x{resolution[1]}".encode("utf-8"))
    return h.hexdigest()
