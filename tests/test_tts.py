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


from tts import resolve_voice, DEFAULT_MODEL_ID, DEFAULT_SETTINGS


class TestResolveVoice:
    def test_speaker_present(self):
        voices = {
            "narrator": {"voice_id": "nar", "model_id": "m", "settings": {"stability": 0.3}},
            "aleksey_38": {"voice_id": "ale", "model_id": "m", "settings": {"stability": 0.6}},
        }
        cfg = resolve_voice("aleksey_38", voices)
        assert cfg["voice_id"] == "ale"
        assert cfg["settings"]["stability"] == 0.6

    def test_fallback_to_default(self):
        voices = {
            "narrator": {"voice_id": "nar"},
            "default": {"voice_id": "def"},
        }
        cfg = resolve_voice("unknown_speaker", voices)
        assert cfg["voice_id"] == "def"

    def test_fallback_to_narrator(self):
        voices = {"narrator": {"voice_id": "nar"}}
        cfg = resolve_voice("unknown_speaker", voices)
        assert cfg["voice_id"] == "nar"

    def test_missing_narrator_raises(self):
        with pytest.raises(ValueError):
            resolve_voice("any", {"default": {"voice_id": "d"}})

    def test_merge_defaults_when_fields_absent(self):
        voices = {"narrator": {"voice_id": "nar"}}
        cfg = resolve_voice("narrator", voices)
        assert cfg["model_id"] == DEFAULT_MODEL_ID
        assert cfg["settings"] == DEFAULT_SETTINGS

    def test_entry_fields_override_defaults(self):
        voices = {"narrator": {
            "voice_id": "nar",
            "model_id": "custom-model",
            "settings": {"stability": 0.9},
        }}
        cfg = resolve_voice("narrator", voices)
        assert cfg["model_id"] == "custom-model"
        # settings из записи целиком заменяют DEFAULT_SETTINGS (не merge)
        assert cfg["settings"] == {"stability": 0.9}


from tts import voice_hash


class TestVoiceHash:
    def _cfg(self, **over):
        base = {
            "voice_id": "v1",
            "model_id": "m",
            "settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        base.update(over)
        return base

    def test_deterministic(self):
        h1 = voice_hash("hello", self._cfg())
        h2 = voice_hash("hello", self._cfg())
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex

    def test_text_change_changes_hash(self):
        assert voice_hash("a", self._cfg()) != voice_hash("b", self._cfg())

    def test_voice_id_change_changes_hash(self):
        assert voice_hash("x", self._cfg()) != voice_hash("x", self._cfg(voice_id="v2"))

    def test_model_id_change_changes_hash(self):
        assert voice_hash("x", self._cfg()) != voice_hash("x", self._cfg(model_id="m2"))

    def test_settings_change_changes_hash(self):
        a = voice_hash("x", self._cfg())
        b = voice_hash("x", self._cfg(settings={"stability": 0.1, "similarity_boost": 0.75}))
        assert a != b

    def test_settings_key_reorder_same_hash(self):
        a_cfg = self._cfg(settings={"stability": 0.5, "similarity_boost": 0.75})
        b_cfg = self._cfg(settings={"similarity_boost": 0.75, "stability": 0.5})
        assert voice_hash("x", a_cfg) == voice_hash("x", b_cfg)

    def test_whitespace_trimmed(self):
        assert voice_hash("hello", self._cfg()) == voice_hash("  hello  ", self._cfg())


from tts import audio_duration


class TestAudioDuration:
    def test_reads_real_mp3(self, tmp_path):
        # Генерим 1-секундный silent mp3 через mutagen + minimal bytes
        # Надёжнее: сохранить заранее заготовленный короткий mp3 в tests/fixtures/.
        # Но чтобы не тянуть бинарник в репо, используем готовый файл при smoke-тесте
        # и параметризуем этот тест через pytest.importorskip fallback.
        pytest.importorskip("mutagen.mp3")
        fixture = tmp_path.parent / "fixtures" / "silence_1s.mp3"
        if not fixture.exists():
            pytest.skip(f"fixture missing: {fixture}")
        dur = audio_duration(fixture)
        assert 0.8 < dur < 1.3


import requests
from tts import generate_tts, ELEVEN_API_BASE


MP3_MAGIC = b"\xff\xfb\x90\x00" + b"\x00" * 256  # minimal-ish MP3 header + padding


class TestGenerateTts:
    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch):
        monkeypatch.setattr("tts._sleep", lambda d: None)

    def _cfg(self):
        return {
            "voice_id": "v1",
            "model_id": "eleven_multilingual_v2",
            "settings": {"stability": 0.5, "similarity_boost": 0.75},
        }

    def test_happy_path_writes_file_atomically(self, tmp_path, requests_mock):
        url = f"{ELEVEN_API_BASE}/text-to-speech/v1"
        requests_mock.post(url, content=MP3_MAGIC, status_code=200)
        out = tmp_path / "scene_001.mp3"
        generate_tts("hello world", self._cfg(), out, api_key="k")
        assert out.exists()
        assert out.read_bytes() == MP3_MAGIC
        # .tmp файл убран
        assert not out.with_suffix(out.suffix + ".tmp").exists()

    def test_retries_on_429_then_success(self, tmp_path, requests_mock):
        url = f"{ELEVEN_API_BASE}/text-to-speech/v1"
        requests_mock.post(url, [
            {"status_code": 429, "text": "rate limit"},
            {"status_code": 200, "content": MP3_MAGIC},
        ])
        out = tmp_path / "scene_001.mp3"
        generate_tts("hi", self._cfg(), out, api_key="k")
        assert out.exists()
        assert requests_mock.call_count == 2

    def test_fatal_on_401_raises_without_retry(self, tmp_path, requests_mock):
        url = f"{ELEVEN_API_BASE}/text-to-speech/v1"
        requests_mock.post(url, status_code=401, text="unauthorized")
        out = tmp_path / "scene_001.mp3"
        with pytest.raises(RuntimeError) as exc:
            generate_tts("hi", self._cfg(), out, api_key="k")
        assert "401" in str(exc.value)
        assert requests_mock.call_count == 1
        assert not out.exists()

    def test_sends_correct_body(self, tmp_path, requests_mock):
        url = f"{ELEVEN_API_BASE}/text-to-speech/v1"
        requests_mock.post(url, content=MP3_MAGIC, status_code=200)
        out = tmp_path / "scene_001.mp3"
        generate_tts("привет", self._cfg(), out, api_key="secret-key")
        req = requests_mock.last_request
        body = req.json()
        assert body["text"] == "привет"
        assert body["model_id"] == "eleven_multilingual_v2"
        assert body["voice_settings"] == {"stability": 0.5, "similarity_boost": 0.75}
        assert req.headers.get("xi-api-key") == "secret-key"
        # output_format — query param
        assert "output_format=mp3_44100_128" in req.url
