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
