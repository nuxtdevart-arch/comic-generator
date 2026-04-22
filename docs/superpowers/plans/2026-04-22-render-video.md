# `--render-video` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать `--render-video` / `--render-video-only` — финальный mp4 (кадры + аудио + hard-sub ASS) одной командой.

**Architecture:** Новый модуль `video.py` (паттерн `tts.py`), оркестрация из `main()`. Per-scene ffmpeg + concat demuxer. ASS-формат для стилизованных субтитров из `design_spec.json`. Hash-кэш per-scene mp4 для идемпотентного resume.

**Tech Stack:** Python 3.14 stdlib (subprocess, hashlib, pathlib). ffmpeg + ffprobe системные бинари. pytest + unittest.mock для тестов. libx264/libass в ffmpeg.

**Spec:** `docs/superpowers/specs/2026-04-22-render-video-design.md`.

**Структура файлов:**

- **Создать:** `video.py` — все функции рендера (паттерн как `tts.py`).
- **Создать:** `tests/test_video.py` — unit-тесты чистых функций.
- **Создать:** `tests/test_video_integration.py` — smoke test на реальных ассетах, `@pytest.mark.integration`.
- **Создать:** `pytest.ini` — регистрация `integration` marker.
- **Модифицировать:** `generate_comic.py` — `Scene` dataclass (+3 поля), `main()` (+флаги + стадии).
- **Модифицировать:** `README.md` — раздел `--render-video`.
- **Модифицировать:** `TODO.md` — вычеркнуть сделанное в разделе 3.
- **Модифицировать:** `CLAUDE.md` — архитектура + статус + roadmap.

**Реальные поля `design_spec.json`** (проверено на существующем файле):

```json
{
  "font_family": "Arial",
  "font_weight": 600,
  "font_size_px": 42,
  "color_fg": "#F0F0F0",
  "stroke_px": 2,
  "stroke_color": "#000000",
  "position": "bottom_centered",
  "margin_bottom_pct": 8,
  "max_chars_per_line": 42,
  "max_lines": 2
}
```

Маппинг (обновлён относительно черновика в спеке):

| design_spec поле | ASS Style поле |
|---|---|
| `font_family` | `Fontname` |
| `font_size_px` | `Fontsize` |
| `color_fg` → BGR | `PrimaryColour` |
| `stroke_color` → BGR | `OutlineColour` |
| `stroke_px` | `Outline` |
| `position == "bottom_centered"` | `Alignment=2` |
| `margin_bottom_pct` × height / 100 | `MarginV` |

---

## Task 0: Pytest integration marker

**Files:**
- Create: `pytest.ini`

- [ ] **Step 1: Create `pytest.ini` with integration marker**

```ini
[pytest]
markers =
    integration: marks tests as integration (require real ffmpeg + real assets); deselect with '-m "not integration"'
addopts = -m "not integration"
```

- [ ] **Step 2: Verify existing tests still run**

Run: `pytest tests/ -v`
Expected: все существующие тесты (test_pure, test_schemas, test_tts) PASS, integration помечены и скипаются автоматически.

- [ ] **Step 3: Commit**

```bash
git add pytest.ini
git commit -m "test(config): register integration marker in pytest.ini"
```

---

## Task 1: ASS time & color formatters

**Files:**
- Create: `video.py`
- Create: `tests/test_video.py`

- [ ] **Step 1: Write failing tests**

`tests/test_video.py`:

```python
"""Unit tests for video.py pure helpers."""
import pytest

from video import _fmt_ass_time, _hex_to_ass_color


class TestFmtAssTime:
    @pytest.mark.parametrize("seconds,expected", [
        (0.0, "0:00:00.00"),
        (3.456, "0:00:03.46"),
        (59.999, "0:01:00.00"),
        (60.0, "0:01:00.00"),
        (3661.5, "1:01:01.50"),
        (28.26448979, "0:00:28.26"),
    ])
    def test_format(self, seconds, expected):
        assert _fmt_ass_time(seconds) == expected


class TestHexToAssColor:
    @pytest.mark.parametrize("hex_in,ass_out", [
        ("#FF0000", "&H000000FF"),  # red  (BGR + alpha)
        ("#00FF00", "&H0000FF00"),  # green
        ("#0000FF", "&H00FF0000"),  # blue
        ("#FFFFFF", "&H00FFFFFF"),  # white
        ("#000000", "&H00000000"),  # black
        ("#F0F0F0", "&H00F0F0F0"),  # design_spec default color_fg
        ("F0F0F0",  "&H00F0F0F0"),  # no leading #
    ])
    def test_conversion(self, hex_in, ass_out):
        assert _hex_to_ass_color(hex_in) == ass_out

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _hex_to_ass_color("not-a-color")
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `pytest tests/test_video.py -v`
Expected: ImportError `video` module not found.

- [ ] **Step 3: Create `video.py` with helpers**

```python
"""Video rendering: ffmpeg per-scene + ASS subtitles + concat.

Pattern mirrors tts.py — standalone module imported by generate_comic.
"""
import logging

log = logging.getLogger("comic.video")


def _fmt_ass_time(seconds: float) -> str:
    """Format seconds as ASS time: H:MM:SS.cc (centiseconds, not ms)."""
    total_cs = int(round(seconds * 100))
    h, cs = divmod(total_cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _hex_to_ass_color(hex_str: str) -> str:
    """Convert #RRGGBB (or RRGGBB) to ASS &H00BBGGRR (BGR + alpha=00)."""
    s = hex_str.lstrip("#").strip()
    if len(s) != 6:
        raise ValueError(f"Invalid hex color: {hex_str!r}")
    try:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
    except ValueError:
        raise ValueError(f"Invalid hex color: {hex_str!r}")
    return f"&H00{b:02X}{g:02X}{r:02X}"
```

- [ ] **Step 4: Run tests — verify PASS**

Run: `pytest tests/test_video.py -v`
Expected: PASS (13 тестов).

- [ ] **Step 5: Commit**

```bash
git add video.py tests/test_video.py
git commit -m "feat(video): add ASS time/color format helpers"
```

---

## Task 2: Quality presets + video hash

**Files:**
- Modify: `video.py`
- Modify: `tests/test_video.py`

- [ ] **Step 1: Add failing tests**

Добавить в `tests/test_video.py`:

```python
from video import QUALITY_PRESETS, compute_video_hash


class TestQualityPresets:
    def test_has_draft_and_final(self):
        assert set(QUALITY_PRESETS.keys()) == {"draft", "final"}

    @pytest.mark.parametrize("name", ["draft", "final"])
    def test_preset_keys(self, name):
        preset = QUALITY_PRESETS[name]
        assert set(preset.keys()) == {"res", "fps", "crf", "preset"}
        assert isinstance(preset["res"], tuple) and len(preset["res"]) == 2

    def test_draft_values(self):
        p = QUALITY_PRESETS["draft"]
        assert p["res"] == (1280, 720)
        assert p["fps"] == 24
        assert p["crf"] == 28
        assert p["preset"] == "ultrafast"

    def test_final_values(self):
        p = QUALITY_PRESETS["final"]
        assert p["res"] == (1920, 1080)
        assert p["fps"] == 30
        assert p["crf"] == 18
        assert p["preset"] == "medium"


class TestComputeVideoHash:
    @pytest.fixture
    def base_args(self, tmp_path):
        img = tmp_path / "img.png"
        img.write_bytes(b"png-bytes")
        audio = tmp_path / "a.mp3"
        audio.write_bytes(b"mp3-bytes")
        return {
            "img_path": img, "audio_path": audio,
            "ass_block": "Dialogue: 0,0:00:00.00,0:00:03.00,Default,,0,0,0,,hi",
            "quality": "draft", "fps": 24, "resolution": (1280, 720),
        }

    def test_stable(self, base_args):
        h1 = compute_video_hash(**base_args)
        h2 = compute_video_hash(**base_args)
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex

    @pytest.mark.parametrize("mutate_key,new_value", [
        ("ass_block", "different"),
        ("quality", "final"),
        ("fps", 30),
        ("resolution", (1920, 1080)),
    ])
    def test_param_changes_hash(self, base_args, mutate_key, new_value):
        h_before = compute_video_hash(**base_args)
        base_args[mutate_key] = new_value
        h_after = compute_video_hash(**base_args)
        assert h_before != h_after

    def test_image_bytes_change_hash(self, base_args):
        h_before = compute_video_hash(**base_args)
        base_args["img_path"].write_bytes(b"different-png-bytes")
        h_after = compute_video_hash(**base_args)
        assert h_before != h_after

    def test_audio_bytes_change_hash(self, base_args):
        h_before = compute_video_hash(**base_args)
        base_args["audio_path"].write_bytes(b"different-mp3-bytes")
        h_after = compute_video_hash(**base_args)
        assert h_before != h_after
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `pytest tests/test_video.py -v`
Expected: ImportError `QUALITY_PRESETS` / `compute_video_hash`.

- [ ] **Step 3: Add implementation to `video.py`**

```python
import hashlib
from pathlib import Path
from typing import Optional


QUALITY_PRESETS: dict[str, dict] = {
    "draft": {"res": (1280, 720),  "fps": 24, "crf": 28, "preset": "ultrafast"},
    "final": {"res": (1920, 1080), "fps": 30, "crf": 18, "preset": "medium"},
}


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
```

- [ ] **Step 4: Run tests — verify PASS**

Run: `pytest tests/test_video.py -v`
Expected: все тесты PASS.

- [ ] **Step 5: Commit**

```bash
git add video.py tests/test_video.py
git commit -m "feat(video): quality presets + video cache hash"
```

---

## Task 3: Scene ASS block

**Files:**
- Modify: `video.py`
- Modify: `tests/test_video.py`

Функция берёт `subtitle_lines` (не `voice_text`!), джойнит через `\N` ASS line-break. Экранирует спецсимволы ASS (`{`, `}`, `\`).

- [ ] **Step 1: Add failing tests**

```python
from video import scene_ass_block


class TestSceneAssBlock:
    def _scene(self, **overrides):
        """Build a minimal dict that mimics Scene attributes used here."""
        base = {
            "voice_text": "long narration " * 20,
            "subtitle_lines": ["Line one.", "Line two.", "Line three."],
        }
        base.update(overrides)
        return type("S", (), base)()

    def test_one_dialogue_line(self):
        scene = self._scene()
        block = scene_ass_block(scene, start_sec=0.0, end_sec=3.5)
        assert block.count("\n") == 0  # single Dialogue line, no trailing newline
        assert block.startswith("Dialogue: 0,0:00:00.00,0:00:03.50,Default,,0,0,0,,")

    def test_joins_with_N(self):
        scene = self._scene()
        block = scene_ass_block(scene, 0.0, 3.5)
        assert "Line one.\\NLine two.\\NLine three." in block

    def test_uses_subtitle_lines_not_voice_text(self):
        scene = self._scene(subtitle_lines=["short"], voice_text="very long narration " * 50)
        block = scene_ass_block(scene, 0.0, 3.5)
        assert "short" in block
        assert "narration" not in block

    def test_fallback_to_voice_text_when_lines_empty(self):
        scene = self._scene(subtitle_lines=[], voice_text="hello world")
        block = scene_ass_block(scene, 0.0, 3.5)
        assert "hello world" in block

    def test_escapes_braces(self):
        scene = self._scene(subtitle_lines=["Hello {world}"])
        block = scene_ass_block(scene, 0.0, 3.5)
        # ASS uses {...} for inline override tags; must escape
        assert "\\{world\\}" in block

    def test_time_format(self):
        scene = self._scene()
        block = scene_ass_block(scene, 28.26, 42.10)
        assert "0:00:28.26,0:00:42.10" in block
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `pytest tests/test_video.py::TestSceneAssBlock -v`
Expected: ImportError.

- [ ] **Step 3: Implement in `video.py`**

```python
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
```

- [ ] **Step 4: Run tests — verify PASS**

Run: `pytest tests/test_video.py::TestSceneAssBlock -v`
Expected: 6 тестов PASS.

- [ ] **Step 5: Commit**

```bash
git add video.py tests/test_video.py
git commit -m "feat(video): scene_ass_block uses subtitle_lines with \\N line-break"
```

---

## Task 4: Export ASS subtitles file

**Files:**
- Modify: `video.py`
- Modify: `tests/test_video.py`

`export_ass` пишет полный `.ass` файл: Script Info + V4+ Styles (из `design_spec`) + Events (через `scene_ass_block`).

- [ ] **Step 1: Add failing tests**

```python
from video import export_ass


class TestExportAss:
    @pytest.fixture
    def design_spec(self):
        return {
            "font_family": "Arial",
            "font_size_px": 42,
            "color_fg": "#F0F0F0",
            "stroke_color": "#000000",
            "stroke_px": 2,
            "position": "bottom_centered",
            "margin_bottom_pct": 8,
        }

    @pytest.fixture
    def scenes(self):
        def mk(lines, dur, status="ok"):
            return type("S", (), {
                "subtitle_lines": lines, "voice_text": "", "text": "",
                "status": status, "audio_duration": dur,
                "duration_sec": dur, "pacing": "normal",
            })()
        return [
            mk(["first"], 2.0),
            mk(["second"], 3.0),
            mk(["third"], 4.0),
        ]

    def test_writes_file(self, tmp_path, design_spec, scenes):
        out = tmp_path / "subs.ass"
        result = export_ass(design_spec, scenes, [2.0, 3.0, 4.0], out, resolution=(1920, 1080))
        assert result == out
        assert out.exists()

    def test_structure(self, tmp_path, design_spec, scenes):
        out = tmp_path / "subs.ass"
        export_ass(design_spec, scenes, [2.0, 3.0, 4.0], out, resolution=(1920, 1080))
        content = out.read_text(encoding="utf-8")
        assert "[Script Info]" in content
        assert "[V4+ Styles]" in content
        assert "[Events]" in content
        assert "Format: Name, Fontname, Fontsize" in content  # V4+ Styles header
        assert "Style: Default,Arial,42," in content

    def test_dialogue_times_cumulative(self, tmp_path, design_spec, scenes):
        out = tmp_path / "subs.ass"
        export_ass(design_spec, scenes, [2.0, 3.0, 4.0], out, resolution=(1920, 1080))
        content = out.read_text(encoding="utf-8")
        # Scene 1: 0.00-2.00
        assert "Dialogue: 0,0:00:00.00,0:00:02.00" in content
        # Scene 2: 2.00-5.00
        assert "Dialogue: 0,0:00:02.00,0:00:05.00" in content
        # Scene 3: 5.00-9.00
        assert "Dialogue: 0,0:00:05.00,0:00:09.00" in content

    def test_skips_non_ok_scenes(self, tmp_path, design_spec):
        scenes = [
            type("S", (), {"subtitle_lines": ["ok one"], "voice_text": "", "text": "",
                           "status": "ok", "audio_duration": 2.0,
                           "duration_sec": 2.0, "pacing": "normal"})(),
            type("S", (), {"subtitle_lines": ["err"], "voice_text": "", "text": "",
                           "status": "error", "audio_duration": 1.0,
                           "duration_sec": 1.0, "pacing": "normal"})(),
        ]
        out = tmp_path / "subs.ass"
        export_ass(design_spec, scenes, [2.0, 1.0], out, resolution=(1920, 1080))
        content = out.read_text(encoding="utf-8")
        assert "ok one" in content
        assert "err" not in content

    def test_resolution_in_playres(self, tmp_path, design_spec, scenes):
        out = tmp_path / "subs.ass"
        export_ass(design_spec, scenes, [2.0, 3.0, 4.0], out, resolution=(1280, 720))
        content = out.read_text(encoding="utf-8")
        assert "PlayResX: 1280" in content
        assert "PlayResY: 720" in content

    def test_margin_from_pct(self, tmp_path, design_spec, scenes):
        out = tmp_path / "subs.ass"
        export_ass(design_spec, scenes, [2.0, 3.0, 4.0], out, resolution=(1920, 1080))
        content = out.read_text(encoding="utf-8")
        # 8% of 1080 = 86
        assert ",86," in content  # MarginV field in Style
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `pytest tests/test_video.py::TestExportAss -v`
Expected: ImportError.

- [ ] **Step 3: Implement in `video.py`**

```python
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
```

- [ ] **Step 4: Run tests — verify PASS**

Run: `pytest tests/test_video.py::TestExportAss -v`
Expected: 6 тестов PASS.

- [ ] **Step 5: Commit**

```bash
git add video.py tests/test_video.py
git commit -m "feat(video): export_ass writes styled subtitles.ass from design_spec"
```

---

## Task 5: ffmpeg check + probe audio duration

**Files:**
- Modify: `video.py`
- Modify: `tests/test_video.py`

- [ ] **Step 1: Add failing tests**

```python
from unittest.mock import patch, MagicMock

from video import check_ffmpeg, probe_audio_duration


class TestCheckFfmpeg:
    def test_ok_when_both_present(self):
        with patch("video.shutil.which", side_effect=lambda x: f"/usr/bin/{x}"):
            check_ffmpeg()  # no raise

    def test_raises_when_ffmpeg_missing(self):
        def fake_which(name):
            return None if name == "ffmpeg" else f"/usr/bin/{name}"
        with patch("video.shutil.which", side_effect=fake_which):
            with pytest.raises(RuntimeError, match="ffmpeg not found"):
                check_ffmpeg()

    def test_raises_when_ffprobe_missing(self):
        def fake_which(name):
            return None if name == "ffprobe" else f"/usr/bin/{name}"
        with patch("video.shutil.which", side_effect=fake_which):
            with pytest.raises(RuntimeError, match="ffprobe not found"):
                check_ffmpeg()


class TestProbeAudioDuration:
    def test_parses_stdout(self, tmp_path):
        fake_mp3 = tmp_path / "a.mp3"
        fake_mp3.write_bytes(b"not a real mp3")
        completed = MagicMock()
        completed.stdout = "28.264489\n"
        completed.returncode = 0
        with patch("video.subprocess.run", return_value=completed):
            dur = probe_audio_duration(fake_mp3)
        assert abs(dur - 28.264489) < 0.001

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            probe_audio_duration(tmp_path / "does_not_exist.mp3")

    def test_ffprobe_error_raises(self, tmp_path):
        fake_mp3 = tmp_path / "a.mp3"
        fake_mp3.write_bytes(b"x")
        completed = MagicMock()
        completed.returncode = 1
        completed.stderr = "invalid data"
        with patch("video.subprocess.run", return_value=completed):
            with pytest.raises(RuntimeError, match="ffprobe failed"):
                probe_audio_duration(fake_mp3)
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `pytest tests/test_video.py::TestCheckFfmpeg tests/test_video.py::TestProbeAudioDuration -v`
Expected: ImportError.

- [ ] **Step 3: Implement in `video.py`**

Добавить в начало `video.py` (верхние импорты):

```python
import shutil
import subprocess
```

И функции:

```python
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
```

- [ ] **Step 4: Run tests — verify PASS**

Run: `pytest tests/test_video.py -v`
Expected: все тесты (включая старые) PASS.

- [ ] **Step 5: Commit**

```bash
git add video.py tests/test_video.py
git commit -m "feat(video): check_ffmpeg + probe_audio_duration"
```

---

## Task 6: Scene dataclass extension

**Files:**
- Modify: `generate_comic.py:116-139`
- Create test entries in `tests/test_video.py`

- [ ] **Step 1: Add test for new Scene fields**

`tests/test_video.py` — добавить:

```python
class TestSceneVideoFields:
    def test_scene_has_video_fields(self):
        from generate_comic import Scene
        s = Scene(index=1, text="hello")
        assert s.video_path == ""
        assert s.video_hash == ""
        assert s.video_status == "pending"

    def test_scene_video_fields_in_asdict(self):
        from generate_comic import Scene
        from dataclasses import asdict
        s = Scene(index=1, text="hello")
        d = asdict(s)
        assert "video_path" in d
        assert "video_hash" in d
        assert "video_status" in d
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `pytest tests/test_video.py::TestSceneVideoFields -v`
Expected: AssertionError — полей нет в Scene.

- [ ] **Step 3: Extend Scene dataclass**

`generate_comic.py`, после строки 139 (`audio_error: str = ""`), добавить (внутри `@dataclass class Scene:`):

```python
    # Video metadata (filled by render_video stage)
    video_path: str = ""
    video_hash: str = ""
    video_status: str = "pending"       # pending | ok | skipped | error
    video_error: str = ""
```

- [ ] **Step 4: Run tests — verify PASS**

Run: `pytest tests/test_video.py::TestSceneVideoFields tests/test_schemas.py tests/test_pure.py -v`
Expected: PASS. Существующие тесты не сломаны.

- [ ] **Step 5: Verify resume compatibility with existing progress.json**

Run: `PYTHONIOENCODING=utf-8 python -c "import json; from generate_comic import Scene; d=json.load(open('output/progress.json',encoding='utf-8')); scenes=[Scene(**s) for s in d['scenes']]; print(f'Loaded {len(scenes)} scenes, video_path[0]={scenes[0].video_path!r}')"`
Expected: без ошибок, `video_path=''`. Dataclass default'ы совместимы.

- [ ] **Step 6: Commit**

```bash
git add generate_comic.py tests/test_video.py
git commit -m "feat(video): Scene dataclass +video_path/hash/status/error"
```

---

## Task 7: Render single scene video

**Files:**
- Modify: `video.py`
- Modify: `tests/test_video.py`
- Create: `tests/test_video_integration.py`

Функция `render_scene_video`: один ffmpeg на сцену. Идемпотентно (hash-check). Атомарная запись. Retry 3× c backoff.

- [ ] **Step 1: Add unit tests (mock subprocess)**

`tests/test_video.py` — добавить:

```python
class TestRenderSceneVideo:
    @pytest.fixture
    def scene(self, tmp_path):
        img = tmp_path / "frame.png"
        img.write_bytes(b"png")
        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"mp3")
        from generate_comic import Scene
        return Scene(
            index=1, text="t",
            subtitle_lines=["hello"],
            status="ok",
            image_path=str(img),
            audio_path=str(audio),
            audio_duration=3.0,
        )

    def test_skips_when_hash_matches(self, tmp_path, scene):
        from video import render_scene_video
        out_mp4 = tmp_path / "video" / "scene_001.mp4"
        out_mp4.parent.mkdir()
        out_mp4.write_bytes(b"existing-video")
        # Precompute expected hash and set it on scene
        ass_path = tmp_path / "subs.ass"
        ass_path.write_text("[Events]\nDialogue: fake\n", encoding="utf-8")
        with patch("video.subprocess.run") as srun:
            from video import compute_video_hash, QUALITY_PRESETS, scene_ass_block
            preset = QUALITY_PRESETS["draft"]
            expected_hash = compute_video_hash(
                img_path=Path(scene.image_path),
                audio_path=Path(scene.audio_path),
                ass_block=scene_ass_block(scene, 0.0, 3.0),
                quality="draft", fps=preset["fps"], resolution=preset["res"],
            )
            scene.video_hash = expected_hash
            scene.video_path = str(out_mp4)
            result = render_scene_video(
                scene=scene, start_sec=0.0, end_sec=3.0,
                ass_path=ass_path, output_dir=out_mp4.parent,
                quality="draft",
            )
            assert result == out_mp4
            srun.assert_not_called()  # skipped

    def test_invokes_ffmpeg_when_hash_mismatch(self, tmp_path, scene):
        from video import render_scene_video
        out_dir = tmp_path / "video"
        out_dir.mkdir()
        ass_path = tmp_path / "subs.ass"
        ass_path.write_text("x", encoding="utf-8")
        completed = MagicMock(returncode=0, stderr="")
        def fake_run(cmd, **kw):
            # ffmpeg must write output path (last arg) to simulate success
            Path(cmd[-1]).write_bytes(b"fake-mp4")
            return completed
        with patch("video.subprocess.run", side_effect=fake_run) as srun:
            result = render_scene_video(
                scene=scene, start_sec=0.0, end_sec=3.0,
                ass_path=ass_path, output_dir=out_dir,
                quality="draft",
            )
        assert result.exists()
        assert srun.call_count == 1
        assert scene.video_status == "ok"
        assert scene.video_hash  # set

    def test_retries_on_failure(self, tmp_path, scene):
        from video import render_scene_video
        out_dir = tmp_path / "video"
        out_dir.mkdir()
        ass_path = tmp_path / "subs.ass"
        ass_path.write_text("x", encoding="utf-8")
        fail = MagicMock(returncode=1, stderr="ffmpeg exploded")
        success = MagicMock(returncode=0, stderr="")
        call_log = []
        def fake_run(cmd, **kw):
            call_log.append(cmd)
            if len(call_log) < 3:
                return fail
            Path(cmd[-1]).write_bytes(b"ok")
            return success
        with patch("video.subprocess.run", side_effect=fake_run):
            with patch("video.time.sleep"):  # skip backoff
                result = render_scene_video(
                    scene=scene, start_sec=0.0, end_sec=3.0,
                    ass_path=ass_path, output_dir=out_dir,
                    quality="draft",
                )
        assert result.exists()
        assert len(call_log) == 3
        assert scene.video_status == "ok"

    def test_sets_error_after_max_retries(self, tmp_path, scene):
        from video import render_scene_video, VIDEO_MAX_RETRIES
        out_dir = tmp_path / "video"
        out_dir.mkdir()
        ass_path = tmp_path / "subs.ass"
        ass_path.write_text("x", encoding="utf-8")
        fail = MagicMock(returncode=1, stderr="ffmpeg exploded")
        with patch("video.subprocess.run", return_value=fail):
            with patch("video.time.sleep"):
                with pytest.raises(RuntimeError, match="ffmpeg failed"):
                    render_scene_video(
                        scene=scene, start_sec=0.0, end_sec=3.0,
                        ass_path=ass_path, output_dir=out_dir,
                        quality="draft",
                    )
        assert scene.video_status == "error"
        assert "ffmpeg exploded" in scene.video_error
```

- [ ] **Step 2: Add integration smoke test** using real assets

`tests/test_video_integration.py`:

```python
"""Integration smoke tests for video rendering.

Requires real ffmpeg + existing output/ assets. Skipped by default.
Run: pytest -m integration tests/test_video_integration.py
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "output"


@pytest.fixture
def tmp_out(tmp_path):
    d = tmp_path / "video"
    d.mkdir()
    return d


@pytest.fixture
def scene_1():
    from generate_comic import Scene
    data = json.loads((OUTPUT / "progress.json").read_text(encoding="utf-8"))
    raw = data["scenes"][0]
    return Scene(**raw)


def test_ffmpeg_available():
    from video import check_ffmpeg
    check_ffmpeg()


def test_render_scene_draft(tmp_out, scene_1):
    from video import (
        render_scene_video, export_ass, probe_audio_duration,
        QUALITY_PRESETS,
    )
    assert Path(scene_1.image_path).exists(), "frame_001.png missing"
    assert Path(scene_1.audio_path).exists(), "scene_001.mp3 missing"

    design_spec = json.loads(
        (OUTPUT / "design_spec.json").read_text(encoding="utf-8")
    )
    real_dur = probe_audio_duration(scene_1.audio_path)
    ass_path = tmp_out / "subs.ass"
    export_ass(design_spec, [scene_1], [real_dur], ass_path,
               resolution=QUALITY_PRESETS["draft"]["res"])

    mp4 = render_scene_video(
        scene=scene_1, start_sec=0.0, end_sec=real_dur,
        ass_path=ass_path, output_dir=tmp_out, quality="draft",
    )
    assert mp4.exists()
    assert mp4.stat().st_size > 10_000  # real mp4 is kilobytes+

    # ffprobe the result
    probe = subprocess.run(
        ["ffprobe", "-v", "error",
         "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,width,height",
         "-of", "json", str(mp4)],
        capture_output=True, text=True,
    )
    info = json.loads(probe.stdout)["streams"][0]
    assert info["codec_name"] == "h264"
    assert info["width"] == 1280
    assert info["height"] == 720
```

- [ ] **Step 3: Implement `render_scene_video` in `video.py`**

Добавить импорт `time` в верхнюю часть `video.py`:

```python
import time
```

Константа и функция:

```python
VIDEO_MAX_RETRIES = 3
VIDEO_RETRY_BACKOFF = [2.0, 8.0]  # seconds between tries


def _build_ffmpeg_cmd(
    image_path: Path, audio_path: Optional[Path], ass_path: Path,
    duration: float, out_tmp: Path, preset: dict,
) -> list[str]:
    w, h = preset["res"]
    # ass filter needs forward slashes even on Windows
    ass_arg = str(ass_path).replace("\\", "/")
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
    cmd += ["-movflags", "+faststart", str(out_tmp)]
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
```

- [ ] **Step 4: Run unit tests — verify PASS**

Run: `pytest tests/test_video.py -v`
Expected: все PASS (включая `TestRenderSceneVideo`).

- [ ] **Step 5: Run integration smoke test on real assets**

Run: `pytest -m integration tests/test_video_integration.py -v`
Expected: PASS. Создан `scene_001.mp4` в tmp, кодек h264, 1280×720.

- [ ] **Step 6: Commit**

```bash
git add video.py tests/test_video.py tests/test_video_integration.py
git commit -m "feat(video): render_scene_video with hash-cache, atomic write, retry"
```

---

## Task 8: Concat scenes into final mp4

**Files:**
- Modify: `video.py`
- Modify: `tests/test_video.py`

- [ ] **Step 1: Add unit tests**

`tests/test_video.py` — добавить:

```python
class TestConcatScenes:
    def test_writes_list_and_invokes_concat(self, tmp_path):
        from video import concat_scenes
        mp4s = []
        for i in range(3):
            p = tmp_path / f"scene_{i+1:03d}.mp4"
            p.write_bytes(b"mp4-" + bytes(str(i), "ascii"))
            mp4s.append(p)
        out = tmp_path / "comic.mp4"
        captured_cmds = []
        def fake_run(cmd, **kw):
            captured_cmds.append(cmd)
            Path(cmd[-1]).write_bytes(b"final-mp4")
            return MagicMock(returncode=0, stderr="")
        with patch("video.subprocess.run", side_effect=fake_run):
            result = concat_scenes(mp4s, out)
        assert result == out
        assert out.exists()
        assert len(captured_cmds) == 1
        cmd = captured_cmds[0]
        assert "-f" in cmd and "concat" in cmd
        assert "-safe" in cmd and "0" in cmd
        assert "-c" in cmd and "copy" in cmd
        # list.txt written next to output
        list_txt = next(tmp_path.glob("*.txt"))
        content = list_txt.read_text(encoding="utf-8")
        assert content.startswith("ffconcat version 1.0")
        for mp4 in mp4s:
            # concat list uses forward slashes (ffmpeg friendly) and 'file' directive
            assert f"file '{str(mp4).replace(chr(92), '/')}'" in content

    def test_empty_list_raises(self, tmp_path):
        from video import concat_scenes
        with pytest.raises(ValueError, match="no scenes"):
            concat_scenes([], tmp_path / "out.mp4")

    def test_ffmpeg_failure_raises(self, tmp_path):
        from video import concat_scenes
        mp4 = tmp_path / "s.mp4"
        mp4.write_bytes(b"x")
        with patch("video.subprocess.run",
                   return_value=MagicMock(returncode=1, stderr="broken")):
            with pytest.raises(RuntimeError, match="concat failed"):
                concat_scenes([mp4], tmp_path / "out.mp4")
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `pytest tests/test_video.py::TestConcatScenes -v`
Expected: ImportError.

- [ ] **Step 3: Implement in `video.py`**

```python
def concat_scenes(scene_mp4s: list[Path], output_path: Path) -> Path:
    """Concatenate per-scene mp4s into final output via concat demuxer (no re-encode)."""
    if not scene_mp4s:
        raise ValueError("Cannot concat: no scenes provided")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_txt = output_path.parent / f"{output_path.stem}_concat.txt"
    lines = ["ffconcat version 1.0"]
    for mp4 in scene_mp4s:
        # ffmpeg concat demuxer wants forward slashes
        p = str(mp4).replace("\\", "/")
        lines.append(f"file '{p}'")
    list_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out_tmp = output_path.with_suffix(".mp4.tmp")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_txt), "-c", "copy", str(out_tmp),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not out_tmp.exists():
        last = (result.stderr or "").strip().splitlines()[-1:] or [""]
        raise RuntimeError(f"concat failed: {last[0]}")
    out_tmp.replace(output_path)
    log.info("🎞️  final video → %s (%d scenes)", output_path, len(scene_mp4s))
    return output_path
```

- [ ] **Step 4: Run tests — verify PASS**

Run: `pytest tests/test_video.py::TestConcatScenes -v`
Expected: 3 теста PASS.

- [ ] **Step 5: Commit**

```bash
git add video.py tests/test_video.py
git commit -m "feat(video): concat_scenes via ffmpeg concat demuxer"
```

---

## Task 9: `render_video` orchestrator

**Files:**
- Modify: `video.py`
- Modify: `tests/test_video.py`

Оркестратор: валидация → export_ass → цикл render_scene_video → concat_scenes.

- [ ] **Step 1: Add unit tests**

`tests/test_video.py` — добавить:

```python
class TestRenderVideoOrchestrator:
    @pytest.fixture
    def scenes_and_files(self, tmp_path):
        from generate_comic import Scene
        out_dir = tmp_path / "output"
        (out_dir / "audio").mkdir(parents=True)
        scenes = []
        for i in range(1, 4):
            img = out_dir / f"frame_{i:03d}.png"
            img.write_bytes(b"png")
            audio = out_dir / "audio" / f"scene_{i:03d}.mp3"
            audio.write_bytes(b"mp3")
            scenes.append(Scene(
                index=i, text="t",
                subtitle_lines=[f"line {i}"],
                status="ok",
                image_path=str(img),
                audio_path=str(audio),
                audio_duration=2.0,
                duration_sec=2.0,
            ))
        design_spec = {
            "font_family": "Arial", "font_size_px": 42,
            "color_fg": "#FFFFFF", "stroke_color": "#000000",
            "stroke_px": 2, "position": "bottom_centered",
            "margin_bottom_pct": 8,
        }
        return scenes, design_spec, out_dir

    def test_fail_fast_missing_image(self, scenes_and_files, tmp_path):
        from video import render_video
        scenes, design_spec, out_dir = scenes_and_files
        Path(scenes[1].image_path).unlink()
        with pytest.raises(RuntimeError, match="missing image"):
            render_video(
                scenes=scenes, design_spec=design_spec,
                quality="draft", output=tmp_path / "comic.mp4",
                allow_incomplete=False, output_dir=out_dir,
            )

    def test_allow_incomplete_skips_missing(self, scenes_and_files, tmp_path):
        from video import render_video
        scenes, design_spec, out_dir = scenes_and_files
        Path(scenes[1].image_path).unlink()
        def fake_run(cmd, **kw):
            Path(cmd[-1]).write_bytes(b"mp4")
            return MagicMock(returncode=0, stderr="")
        with patch("video.subprocess.run", side_effect=fake_run):
            with patch("video.check_ffmpeg"):
                result = render_video(
                    scenes=scenes, design_spec=design_spec,
                    quality="draft", output=tmp_path / "comic.mp4",
                    allow_incomplete=True, output_dir=out_dir,
                )
        assert result.exists()
        assert scenes[1].video_status == "skipped"

    def test_full_path_invokes_ffmpeg_per_scene_plus_concat(
        self, scenes_and_files, tmp_path,
    ):
        from video import render_video
        scenes, design_spec, out_dir = scenes_and_files
        call_log = []
        def fake_run(cmd, **kw):
            call_log.append(cmd[0:2])
            Path(cmd[-1]).write_bytes(b"mp4")
            return MagicMock(returncode=0, stderr="")
        with patch("video.subprocess.run", side_effect=fake_run):
            with patch("video.check_ffmpeg"):
                render_video(
                    scenes=scenes, design_spec=design_spec,
                    quality="draft", output=tmp_path / "comic.mp4",
                    allow_incomplete=False, output_dir=out_dir,
                )
        # 3 per-scene + 1 concat
        assert len(call_log) == 4

    def test_idempotent_second_run(self, scenes_and_files, tmp_path):
        """Second run skips per-scene ffmpeg (hash match), runs only concat."""
        from video import render_video
        scenes, design_spec, out_dir = scenes_and_files
        def fake_run(cmd, **kw):
            Path(cmd[-1]).write_bytes(b"mp4")
            return MagicMock(returncode=0, stderr="")
        with patch("video.subprocess.run", side_effect=fake_run):
            with patch("video.check_ffmpeg"):
                render_video(
                    scenes=scenes, design_spec=design_spec,
                    quality="draft", output=tmp_path / "comic.mp4",
                    allow_incomplete=False, output_dir=out_dir,
                )
        # second call
        call_log = []
        def fake_run2(cmd, **kw):
            call_log.append(cmd[0:2])
            Path(cmd[-1]).write_bytes(b"mp4")
            return MagicMock(returncode=0, stderr="")
        with patch("video.subprocess.run", side_effect=fake_run2):
            with patch("video.check_ffmpeg"):
                render_video(
                    scenes=scenes, design_spec=design_spec,
                    quality="draft", output=tmp_path / "comic.mp4",
                    allow_incomplete=False, output_dir=out_dir,
                )
        # only concat, no per-scene
        assert len(call_log) == 1
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `pytest tests/test_video.py::TestRenderVideoOrchestrator -v`
Expected: ImportError.

- [ ] **Step 3: Implement `render_video` in `video.py`**

```python
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
```

- [ ] **Step 4: Run tests — verify PASS**

Run: `pytest tests/test_video.py -v`
Expected: все PASS.

- [ ] **Step 5: Commit**

```bash
git add video.py tests/test_video.py
git commit -m "feat(video): render_video orchestrator with fail-fast + allow-incomplete"
```

---

## Task 10: CLI integration — flags and stages

**Files:**
- Modify: `generate_comic.py:856-1000` (argparse + main orchestration)

Добавить 4 флага. Оркестрация: `--render-video-only` — отдельный ранний путь (как `--tts-only`). `--render-video` — стадия в конце основного пайплайна после TTS.

- [ ] **Step 1: Add CLI flags**

В `generate_comic.py`, после строки 885 (`ap.add_argument("--voices", ...)`) добавить:

```python
    ap.add_argument("--render-video", action="store_true",
                    help="Render final mp4 after image + TTS stages (uses ffmpeg).")
    ap.add_argument("--render-video-only", action="store_true",
                    help="Skip all other stages; render final mp4 from existing "
                         "output/ (frames + audio + design_spec + progress.json).")
    ap.add_argument("--quality", choices=["draft", "final"], default="draft",
                    help="Video quality preset. draft=720p/ultrafast, final=1080p/medium.")
    ap.add_argument("--output", type=Path, default=None,
                    help="Path for final mp4 (default: output/comic.mp4).")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="Skip scenes missing image/audio instead of fail-fast.")
```

- [ ] **Step 2: Update story-required check**

Строка 888 (было `if not args.tts_only and not args.story:`), заменить на:

```python
    if not (args.tts_only or args.render_video_only) and not args.story:
        sys.exit("ERROR: --story required unless --tts-only or --render-video-only is set")
```

- [ ] **Step 3: Add render-video-only early path**

После блока `if args.tts_only:` (строки 927-~970, найти конец блока через грепание `if args.tts_only:` до следующего `if ` того же уровня indentation) добавить:

```python
    if args.render_video_only:
        if not progress_path.exists():
            sys.exit(f"ERROR: --render-video-only requires {progress_path}")
        if not design_spec_path.exists():
            sys.exit(f"ERROR: --render-video-only requires {design_spec_path}")
        import video as video_mod
        data = json.loads(progress_path.read_text(encoding="utf-8"))
        scenes = [Scene(**s) for s in data["scenes"]]
        design_spec = json.loads(design_spec_path.read_text(encoding="utf-8"))
        output_path = args.output or (out_dir / "comic.mp4")
        log.info("Render-video-only stage: %s (quality=%s)", output_path, args.quality)
        try:
            final_mp4 = video_mod.render_video(
                scenes=scenes, design_spec=design_spec,
                quality=args.quality, output=output_path,
                allow_incomplete=args.allow_incomplete,
                output_dir=out_dir,
                save_progress_fn=lambda: save_progress(progress_path, scenes),
            )
        except RuntimeError as e:
            sys.exit(f"ERROR: {e}")
        log.info("Final video: %s", final_mp4)
        return
```

- [ ] **Step 4: Add render-video stage at end of normal pipeline**

В конце функции `main()`, после завершения TTS-стадии (перед закрывающей скобкой main, после финального `export_srt(...)`), добавить:

```python
    if args.render_video:
        if not design_spec_path.exists():
            log.error("--render-video requires design_spec.json; skipping.")
        else:
            import video as video_mod
            design_spec = json.loads(design_spec_path.read_text(encoding="utf-8"))
            output_path = args.output or (out_dir / "comic.mp4")
            log.info("Render-video stage: %s (quality=%s)", output_path, args.quality)
            try:
                final_mp4 = video_mod.render_video(
                    scenes=scenes, design_spec=design_spec,
                    quality=args.quality, output=output_path,
                    allow_incomplete=args.allow_incomplete,
                    output_dir=out_dir,
                    save_progress_fn=lambda: save_progress(progress_path, scenes),
                )
                log.info("Final video: %s", final_mp4)
            except RuntimeError as e:
                log.error("Video render failed: %s", e)
```

(Exact line for insertion — найди поиском `export_srt(scenes, srt_path)` в конце main. Вставить НЕПОСРЕДСТВЕННО ПОСЛЕ этого вызова.)

- [ ] **Step 5: Smoke test — CLI parsing**

Run: `python generate_comic.py --help 2>&1 | grep -E "render-video|quality|allow-incomplete|output"`
Expected: все 5 новых флагов видны.

- [ ] **Step 6: Smoke test — render-video-only on real data**

Run: `python generate_comic.py --render-video-only --quality draft --allow-incomplete --limit-note --output output/comic_test.mp4 2>&1 | tail -20`

(убрать `--limit-note` — это не флаг, только для ориентира; фактическая команда:)

Run: `python generate_comic.py --render-video-only --quality draft --allow-incomplete --output output/comic_test.mp4 2>&1 | tail -30`
Expected: логи «Render-video-only stage», per-scene рендеры, concat, итоговый `output/comic_test.mp4` создан.

Проверить:
```bash
ls -la output/comic_test.mp4 output/video/scene_*.mp4 | head -10
ffprobe -v error -show_entries format=duration output/comic_test.mp4
```

Если работает — открыть `output/comic_test.mp4` в плеере. Субтитры видны, аудио синхронно.

- [ ] **Step 7: Smoke test — idempotency**

Повторить команду из Step 6. Expected: логи «cached, skip» для всех сцен, только concat пересобирается.

- [ ] **Step 8: Commit**

```bash
git add generate_comic.py
git commit -m "feat(cli): --render-video / --render-video-only / --quality / --output"
```

---

## Task 11: Documentation updates

**Files:**
- Modify: `README.md`
- Modify: `TODO.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add `--render-video` section to `README.md`**

Найти секцию про `--tts` (в `README.md`). Добавить после неё новую секцию:

```markdown
### `--render-video` / `--render-video-only` — финальный mp4

Собирает готовый mp4 из кадров + аудио + субтитров с вшитой стилизацией из `design_spec.json`.

**Требования:** `ffmpeg` + `ffprobe` в PATH. Установка: https://ffmpeg.org.

**Автостадия** (после полного пайплайна):

```bash
python generate_comic.py --story story.txt --bootstrap --batch --tts --render-video
```

**Standalone** (использует готовые ассеты в `output/`):

```bash
python generate_comic.py --render-video-only --quality draft
python generate_comic.py --render-video-only --quality final --output release.mp4
```

**Флаги:**

- `--quality draft|final` — `draft` 1280×720/ultrafast (для итераций), `final` 1920×1080/medium (для релиза). Default: `draft`.
- `--output PATH` — путь итогового mp4. Default: `output/comic.mp4`.
- `--allow-incomplete` — сцены без кадра/аудио скипаются вместо fail-fast.

**Кэш:** per-scene mp4 в `output/video/scene_NNN.mp4` с hash-ключом. Правка одной сцены → перерендер только её. Смена `--quality` → перерендер всех.

**Где берутся субтитры:** текст из `subtitle_lines` (не `voice_text`), стили из `design_spec.json`, длительность = `audio_duration` (реальная длина mp3).

**Ограничения первой итерации:** hard-cut между сценами (без crossfade), статичные кадры (без Ken Burns), без фоновой музыки. 16:9 только.
```

- [ ] **Step 2: Mark done items in `TODO.md`**

В `TODO.md` раздел 3:

```markdown
## 3. Видеосборка (`--render-video`)

- ✅ **Базовая склейка** (2026-04-22): каждая сцена → клип `effective_duration` с картинкой + аудио + hard-sub ASS. Concat demuxer, quality presets draft/final, hash-кэш.
- ✅ **Burn-in субтитров** (2026-04-22): ASS-формат из `design_spec.json` (font/color/stroke/position), `subtitle_lines` с `\N` line-break.
- 🟡 **Ken Burns эффект** (медленный pan/zoom) на статичных кадрах — убирает ощущение слайдшоу.
- 🟡 **Crossfade** между сценами (0.3–0.5с) вместо жёсткой склейки.
- 🟢 **Бэкграунд-музыка**: `--bgm path/to/track.mp3` с auto-ducking.
- 🟢 **Разные соотношения сторон**: генерация 9:16 варианта для вертикального видео.
```

В разделе «Приоритеты» — обновить пункт 2:

```markdown
2. ✅ **`--render-video`** (пункт 3) — финальный mp4 одной командой (апрель 2026).
3. **`--scene N` и параллельная генерация** (пункт 1) — быстрый итеративный цикл правок.
4. **Unit-тесты + schema validation** (пункт 8) — фундамент для всего остального.
...
```

- [ ] **Step 3: Update `CLAUDE.md`**

Секция «Архитектура», добавить в диаграмму пайплайна:

```
       ├─ TTS stage ────────► output/audio/scene_*.mp3 (ElevenLabs, --tts)
       ├─ SRT export ───────► output/subtitles.srt
       └─ Video render ─────► output/comic.mp4 (--render-video, ffmpeg)
```

Секция «Главные функции», добавить строки:

```markdown
| `video.check_ffmpeg` | video.py | Верификация ffmpeg+ffprobe в PATH |
| `video.export_ass` | video.py | ASS-субтитры из design_spec + scenes |
| `video.render_scene_video` | video.py | Один scene.mp4, hash-cached, atomic |
| `video.concat_scenes` | video.py | Склейка через concat demuxer |
| `video.render_video` | video.py | Оркестратор стадии рендера |
```

Секция «Статус: что сделано» — добавить:

```markdown
- ✅ **Видеосборка (`--render-video`)** — ffmpeg per-scene + concat demuxer, ASS burn-in из `design_spec`, quality presets draft/final, hash-кэш (апрель 2026).
```

Секция «Roadmap» — обновить:

```markdown
1. ✅ **TTS-интеграция** — апрель 2026.
2. ✅ **`--render-video`** — апрель 2026.
3. **`--scene N` + параллельная генерация** (TODO раздел 1)
4. **Usage tracking + `--estimate`** (TODO раздел 6)
5. **Рефакторинг монолита** (TODO раздел 9)
```

Секция «Частые команды» — добавить:

```bash
# Финальный mp4 из готовых ассетов
python generate_comic.py --render-video-only --quality final

# Полный пайплайн с видео
python generate_comic.py --story story.txt --bootstrap --batch --tts --render-video
```

- [ ] **Step 4: Commit**

```bash
git add README.md TODO.md CLAUDE.md
git commit -m "docs(render-video): README/TODO/CLAUDE.md updates"
```

---

## Task 12: Final smoke test & merge

**Files:** none (validation only)

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: всё зелёное, integration скипаются.

- [ ] **Step 2: Run integration smoke test**

Run: `pytest -m integration tests/test_video_integration.py -v`
Expected: PASS. Real ffmpeg render работает.

- [ ] **Step 3: Full manual pipeline smoke**

```bash
# Clean draft render на существующих output/
rm -f output/comic.mp4 output/subtitles.ass
rm -rf output/video/
python generate_comic.py --render-video-only --quality draft --allow-incomplete
```

Expected:
- `output/subtitles.ass` создан.
- `output/video/scene_NNN.mp4` — один mp4 на каждую сцену со `status=ok` и наличием frame/audio.
- `output/comic.mp4` создан.
- Длительность ≈ сумма `audio_duration` всех успешных сцен.

Проверить:
```bash
ffprobe -v error -show_entries format=duration output/comic.mp4
```

- [ ] **Step 4: Visual check**

Открыть `output/comic.mp4` в плеере (mpv / VLC / Windows Media Player):
- Субтитры видны (стиль из design_spec).
- Аудио синхронно с картинкой.
- Переходы резкие (ожидаемо для MVP).
- Нет визуальных артефактов у hard-sub.

- [ ] **Step 5: Idempotency check**

```bash
python generate_comic.py --render-video-only --quality draft --allow-incomplete
```

Expected: логи «🎬 scene N: cached, skip» для всех сцен, только concat пересобирается. Run time < 5с.

- [ ] **Step 6: Quality switch check**

```bash
python generate_comic.py --render-video-only --quality final --output output/comic_final.mp4 --allow-incomplete
```

Expected: все сцены пересобраны (hash не совпал из-за смены quality), 1080p output.

Проверить:
```bash
ffprobe -v error -select_streams v:0 -show_entries stream=width,height output/comic_final.mp4
```

Expected: `width=1920`, `height=1080`.

- [ ] **Step 7: Commit anything remaining**

Если после smoke test остались изменения (например, обновлённый `progress.json` с `video_path`/`video_hash`) — их в `.gitignore`, коммитить не надо. Только если были правки кода/доков.

- [ ] **Step 8: Merge to master**

(если работали в worktree/ветке)

```bash
git log --oneline master..HEAD  # просмотреть коммиты фичи
git checkout master
git merge --no-ff <feature-branch>
git branch -d <feature-branch>
```

---

## Self-Review Checklist

**Spec coverage:**

- [x] Базовая склейка → Task 7 (per-scene) + Task 8 (concat)
- [x] Hard-sub через ASS → Task 4 (export_ass)
- [x] Quality presets draft/final → Task 2
- [x] `--render-video` + `--render-video-only` → Task 10
- [x] Hash-cache per scene mp4 → Task 2 (compute_video_hash) + Task 7 (render_scene_video skips on match)
- [x] Fail-fast + `--allow-incomplete` → Task 9 (render_video)
- [x] Atomic write → Task 7 (out_tmp → replace)
- [x] Retry on ffmpeg failure → Task 7
- [x] `effective_duration` mirror → Task 9 (`_effective_duration_for_video`)
- [x] Unit tests для всех чистых функций → Tasks 1-4, 7-9
- [x] Integration smoke test на реальных ассетах → Task 7
- [x] CLAUDE.md / README / TODO обновления → Task 11

**Placeholder scan:** пройдено, всех конкретный код есть в тасках.

**Type consistency:**

- `render_scene_video(scene, start_sec, end_sec, ass_path, output_dir, quality)` — сигнатура едина между задачами Task 7 и Task 9.
- `render_video(scenes, design_spec, quality, output, allow_incomplete, output_dir, save_progress_fn=None)` — едина между Task 9 и Task 10.
- `export_ass(design_spec, scenes, durations, out_path, resolution)` — едина между Task 4 и Task 9.
- `QUALITY_PRESETS["draft"]["res"] = (1280, 720)` — используется одинаково везде.
- Scene поля `video_path / video_hash / video_status / video_error` — объявлены в Task 6, используются в Task 7/9.
