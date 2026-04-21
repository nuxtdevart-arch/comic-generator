"""Unit tests for tts.py."""
import json
import pytest

from tts import load_voices


class TestLoadVoices:
    def test_ok(self, tmp_path):
        path = tmp_path / "voices.json"
        path.write_text(json.dumps({
            "narrator": {"voice_id": "v1"},
        }), encoding="utf-8")
        voices = load_voices(path)
        assert voices["narrator"]["voice_id"] == "v1"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_voices(tmp_path / "nope.json")

    def test_malformed_json_raises(self, tmp_path):
        path = tmp_path / "voices.json"
        path.write_text("{ not json", encoding="utf-8")
        with pytest.raises(ValueError) as exc:
            load_voices(path)
        assert "voices.json" in str(exc.value).lower() or "json" in str(exc.value).lower()

    def test_missing_narrator_raises(self, tmp_path):
        path = tmp_path / "voices.json"
        path.write_text(json.dumps({"default": {"voice_id": "v1"}}), encoding="utf-8")
        with pytest.raises(ValueError) as exc:
            load_voices(path)
        assert "narrator" in str(exc.value).lower()
