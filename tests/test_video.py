"""Unit tests for video.py pure helpers."""
import pytest
from pathlib import Path

from video import _fmt_ass_time, _hex_to_ass_color, QUALITY_PRESETS, compute_video_hash, scene_ass_block


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
