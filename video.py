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


def _escape_ass_text(text: str) -> str:
    """Escape ASS-special chars in dialogue text."""
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def scene_ass_block(scene, start_sec: float, end_sec: float) -> str:
    """Build single Dialogue line for a scene.

    Uses subtitle_lines (compact screen text), not voice_text (full TTS narration).
    """
    lines = getattr(scene, "subtitle_lines", None) or []
    if not lines:
        fallback = getattr(scene, "voice_text", "") or getattr(scene, "text", "")
        lines = [fallback] if fallback else [""]
    escaped = [_escape_ass_text(s) for s in lines]
    text = "\\N".join(escaped)
    return (
        f"Dialogue: 0,{_fmt_ass_time(start_sec)},{_fmt_ass_time(end_sec)},"
        f"Default,,0,0,0,,{text}"
    )


_POSITION_TO_ALIGNMENT = {
    "bottom_centered": 2, "bottom_center": 2, "bottom-center": 2,
    "bottom_left": 1, "bottom_right": 3,
    "mid_centered": 5, "middle_center": 5,
    "top_centered": 8, "top_center": 8,
}


def _style_line_from_spec(design_spec: dict, resolution: tuple[int, int]) -> str:
    """Build 'Style: Default,...' line from design_spec."""
    font = design_spec.get("font_family", "Arial")
    size = int(design_spec.get("font_size_px", 42))
    primary = _hex_to_ass_color(design_spec.get("color_fg", "#FFFFFF"))
    outline_color = _hex_to_ass_color(design_spec.get("stroke_color", "#000000"))
    outline = int(design_spec.get("stroke_px", 2))
    alignment = _POSITION_TO_ALIGNMENT.get(design_spec.get("position", "bottom_centered"), 2)
    margin_v = int(resolution[1] * design_spec.get("margin_bottom_pct", 8) / 100)
    # V4+ Style fields (30):
    # Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour,
    # Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle,
    # Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
    return (
        f"Style: Default,{font},{size},{primary},&H000000FF,{outline_color},&H00000000,"
        f"0,0,0,0,100,100,0,0,1,{outline},0,{alignment},20,20,{margin_v},1"
    )


_ASS_HEADER_TEMPLATE = """\
[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def export_ass(
    design_spec: dict,
    scenes: list,
    effective_durations: list[float],
    out_path: Path,
    resolution: tuple[int, int],
) -> Path:
    """Write a standalone subtitles.ass from design_spec + scenes."""
    w, h = resolution
    style_line = _style_line_from_spec(design_spec, resolution)
    header = _ASS_HEADER_TEMPLATE.format(w=w, h=h, style=style_line)
    events: list[str] = []
    cursor = 0.0
    for scene, dur in zip(scenes, effective_durations):
        if getattr(scene, "status", "ok") != "ok":
            continue
        start, end = cursor, cursor + dur
        cursor = end
        events.append(scene_ass_block(scene, start, end))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    log.info("ASS exported → %s (%d cues)", out_path, len(events))
    return out_path
