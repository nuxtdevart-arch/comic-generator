"""Video rendering: ffmpeg per-scene + ASS subtitles + concat.

Pattern mirrors tts.py — standalone module imported by generate_comic.
"""
import logging

log = logging.getLogger("comic.video")


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
