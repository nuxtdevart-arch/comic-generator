"""Unit tests for video.py pure helpers."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from video import _fmt_ass_time, _hex_to_ass_color, QUALITY_PRESETS, compute_video_hash, scene_ass_block, export_ass


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
            scene.video_status = "ok"
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
