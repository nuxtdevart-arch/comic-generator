"""Video rendering: ffmpeg per-scene + ASS subtitles + concat.

Pattern mirrors tts.py — standalone module imported by generate_comic.
"""
import logging
import hashlib
import shutil
import subprocess
import time
import os
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


def check_ffmpeg() -> None:
    """Verify ffmpeg and ffprobe are on PATH. Fail-fast with helpful message."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg not found on PATH. Install from https://ffmpeg.org and "
            "ensure ffmpeg is callable from the shell."
        )
    if shutil.which("ffprobe") is None:
        raise RuntimeError(
            "ffprobe not found on PATH (usually shipped with ffmpeg). "
            "Re-install ffmpeg from https://ffmpeg.org."
        )


def probe_audio_duration(mp3_path) -> float:
    """Return audio duration in seconds via ffprobe."""
    p = Path(mp3_path)
    if not p.exists():
        raise FileNotFoundError(f"Audio not found: {p}")
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(p),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {p}: {result.stderr.strip()}")
    return float(result.stdout.strip())


VIDEO_MAX_RETRIES = 3
VIDEO_RETRY_BACKOFF = [2.0, 8.0]  # seconds between tries


def _build_ffmpeg_cmd(
    image_path: Path, audio_path: Optional[Path], ass_path: Path,
    duration: float, out_tmp: Path, preset: dict,
) -> list[str]:
    w, h = preset["res"]
    # ass filter needs forward slashes even on Windows
    ass_arg = str(ass_path).replace("\\", "/")
    # Escape colon for ffmpeg filter string
    ass_arg = ass_arg.replace(":", "\\:")
    vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease," \
         f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,ass='{ass_arg}'"
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
    ]
    if audio_path is not None and Path(audio_path).exists():
        cmd += ["-i", str(audio_path)]
    cmd += [
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-crf", str(preset["crf"]),
        "-preset", preset["preset"],
        "-pix_fmt", "yuv420p",
        "-r", str(preset["fps"]),
    ]
    if audio_path is not None and Path(audio_path).exists():
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", "-f", "mp4", str(out_tmp)]
    return cmd


def render_scene_video(
    scene,
    start_sec: float,
    end_sec: float,
    ass_path: Path,
    output_dir: Path,
    quality: str,
) -> Path:
    """Render single scene to mp4. Idempotent via hash-check. Atomic write."""
    preset = QUALITY_PRESETS[quality]
    duration = end_sec - start_sec
    image_path = Path(scene.image_path)
    audio_path = Path(scene.audio_path) if scene.audio_path else None

    ass_block = scene_ass_block(scene, start_sec, end_sec)
    expected_hash = compute_video_hash(
        img_path=image_path, audio_path=audio_path, ass_block=ass_block,
        quality=quality, fps=preset["fps"], resolution=preset["res"],
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = output_dir / f"scene_{scene.index:03d}.mp4"

    if (scene.video_hash == expected_hash
            and out_mp4.exists()
            and scene.video_status == "ok"):
        log.info("🎬 scene %d: cached, skip", scene.index)
        return out_mp4

    out_tmp = out_mp4.with_suffix(".mp4.tmp")
    cmd = _build_ffmpeg_cmd(image_path, audio_path, ass_path,
                            duration, out_tmp, preset)

    last_err = ""
    for attempt in range(VIDEO_MAX_RETRIES):
        t0 = time.monotonic()
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and out_tmp.exists():
            out_tmp.replace(out_mp4)
            elapsed = time.monotonic() - t0
            log.info("🎬 scene %d rendered in %.1fs", scene.index, elapsed)
            scene.video_path = str(out_mp4)
            scene.video_hash = expected_hash
            scene.video_status = "ok"
            scene.video_error = ""
            return out_mp4
        last_err = (result.stderr or "").strip().splitlines()[-1:] or [""]
        last_err = last_err[0]
        if attempt < VIDEO_MAX_RETRIES - 1:
            delay = VIDEO_RETRY_BACKOFF[min(attempt, len(VIDEO_RETRY_BACKOFF) - 1)]
            log.warning("scene %d ffmpeg failed (attempt %d/%d): %s — retry in %.1fs",
                        scene.index, attempt + 1, VIDEO_MAX_RETRIES, last_err, delay)
            time.sleep(delay)
        if out_tmp.exists():
            out_tmp.unlink()

    scene.video_status = "error"
    scene.video_error = last_err
    raise RuntimeError(f"ffmpeg failed for scene {scene.index}: {last_err}")


def concat_scenes(scene_mp4s: list[Path], output_path: Path) -> Path:
    """Concatenate per-scene mp4s into final output via concat demuxer (no re-encode)."""
    if not scene_mp4s:
        raise ValueError("Cannot concat: no scenes provided")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_txt = output_path.parent / f"{output_path.stem}_concat.txt"
    lines = ["ffconcat version 1.0"]
    for mp4 in scene_mp4s:
        # ffmpeg concat demuxer wants forward slashes and paths relative to list.txt
        rel_p = os.path.relpath(mp4, output_path.parent)
        p = rel_p.replace("\\", "/")
        lines.append(f"file '{p}'")
    list_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out_tmp = output_path.with_suffix(".mp4.tmp")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_txt), "-c", "copy", "-f", "mp4", str(out_tmp),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not out_tmp.exists():
        last = (result.stderr or "").strip().splitlines()[-1:] or [""]
        raise RuntimeError(f"concat failed: {last[0]}")
    out_tmp.replace(output_path)
    log.info("🎞️  final video → %s (%d scenes)", output_path, len(scene_mp4s))
    return output_path


def _effective_duration_for_video(scene) -> float:
    """Mirror generate_comic.effective_duration logic for video pipeline."""
    if getattr(scene, "audio_duration", 0) and scene.audio_duration > 0:
        return float(scene.audio_duration)
    if getattr(scene, "duration_sec", 0) and scene.duration_sec > 0:
        return float(scene.duration_sec)
    # Last-resort estimate (import lazily to avoid cycle)
    from generate_comic import estimate_duration
    return estimate_duration(scene.voice_text or scene.text,
                             getattr(scene, "pacing", "normal"))


def render_video(
    scenes: list,
    design_spec: dict,
    quality: str,
    output: Path,
    allow_incomplete: bool,
    output_dir: Path,
    save_progress_fn=None,
) -> Path:
    """Orchestrate: validate → export ASS → render per-scene → concat final mp4.

    Args:
        scenes: list of Scene objects (with image_path, audio_path, subtitle_lines).
        design_spec: dict loaded from design_spec.json.
        quality: "draft" or "final".
        output: path to final mp4.
        allow_incomplete: if False, missing image/audio raises; if True, skip.
        output_dir: base output dir (for per-scene mp4s and subs.ass).
        save_progress_fn: optional callback to persist progress.json after each scene.

    Returns:
        Path to final mp4.
    """
    check_ffmpeg()
    if quality not in QUALITY_PRESETS:
        raise ValueError(f"Unknown quality {quality!r}. Use: draft|final")
    preset = QUALITY_PRESETS[quality]

    renderable = []
    for scene in scenes:
        if getattr(scene, "status", "ok") != "ok":
            continue
        img_ok = scene.image_path and Path(scene.image_path).exists()
        aud_ok = scene.audio_path and Path(scene.audio_path).exists()
        if not img_ok:
            msg = f"scene {scene.index}: missing image {scene.image_path!r}"
            if not allow_incomplete:
                raise RuntimeError(msg)
            log.warning("%s — skipping (--allow-incomplete)", msg)
            scene.video_status = "skipped"
            continue
        if not aud_ok:
            msg = f"scene {scene.index}: missing audio {scene.audio_path!r}"
            if not allow_incomplete:
                raise RuntimeError(msg)
            log.warning("%s — skipping (--allow-incomplete)", msg)
            scene.video_status = "skipped"
            continue
        renderable.append(scene)

    if not renderable:
        raise RuntimeError("No renderable scenes (all missing assets or error state)")

    # Compute effective durations for rendered scenes only
    durations = [_effective_duration_for_video(s) for s in renderable]

    # Export ASS (only for scenes that will be rendered, to align timings)
    scene_video_dir = output_dir / "video"
    ass_path = output_dir / "subtitles.ass"
    export_ass(design_spec, renderable, durations, ass_path,
               resolution=preset["res"])

    # Render per-scene
    cursor = 0.0
    mp4s = []
    for scene, dur in zip(renderable, durations):
        start, end = cursor, cursor + dur
        cursor = end
        try:
            mp4 = render_scene_video(
                scene=scene, start_sec=start, end_sec=end,
                ass_path=ass_path, output_dir=scene_video_dir,
                quality=quality,
            )
            mp4s.append(mp4)
        except RuntimeError as e:
            log.error("scene %d failed: %s", scene.index, e)
            # video_status already set to "error" by render_scene_video
        if save_progress_fn:
            save_progress_fn()

    errored = [s for s in renderable if s.video_status == "error"]
    if errored and not allow_incomplete:
        idxs = ", ".join(str(s.index) for s in errored)
        raise RuntimeError(
            f"{len(errored)} scene(s) failed video render: {idxs}. "
            f"Fix and re-run, or use --allow-incomplete."
        )
    if errored:
        idxs = ", ".join(str(s.index) for s in errored)
        log.warning("Concatenating without %d failed scene(s): %s", len(errored), idxs)

    if not mp4s:
        raise RuntimeError("No scenes rendered successfully")

    return concat_scenes(mp4s, output)
