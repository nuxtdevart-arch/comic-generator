# TTS Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить ElevenLabs-only TTS-этап в пайплайн (`--tts`, `--tts-only`), с хеш-кэшем, skip-and-continue error handling и SRT с реальной длительностью аудио.

**Architecture:** Новый модуль `tts.py` на корне рядом с `generate_comic.py`. TTS — отдельный stage после image gen, опционально standalone через `--tts-only`. Голос per-speaker в `voices.json`. Длительность mp3 через `mutagen`. SRT использует реальную длительность когда есть, иначе fallback на `estimate_duration`.

**Tech Stack:** Python 3.14, `requests` (raw HTTP к ElevenLabs), `mutagen` (парсинг mp3 duration), `pytest` + `requests-mock` (тесты). Переиспользуем `classify_error` + `backoff_delay` из `generate_comic.py`.

**Reference:** `docs/superpowers/specs/2026-04-21-tts-integration-design.md`

---

## Task 1: Dependencies + .gitignore

**Files:**
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Add runtime deps**

Append to `requirements.txt`:
```
requests>=2.31
mutagen>=1.47
```

- [ ] **Step 2: Add dev dep**

Append to `requirements-dev.txt`:
```
requests-mock>=1.11
```

- [ ] **Step 3: Install + verify**

Run:
```bash
pip install -r requirements.txt -r requirements-dev.txt
python -c "import requests, mutagen, requests_mock; print('ok')"
```
Expected: `ok`.

- [ ] **Step 4: Update .gitignore**

Add after `references/` line:
```
output/audio/
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt requirements-dev.txt .gitignore
git commit -m "chore(tts): add requests, mutagen, requests-mock, gitignore audio"
```

---

## Task 2: voices.json skeleton

**Files:**
- Create: `voices.json`

- [ ] **Step 1: Create `voices.json` с narrator + default**

```json
{
  "narrator": {
    "voice_id": "pNInz6ovClqMvhaFY6HZ",
    "model_id": "eleven_multilingual_v2",
    "settings": {
      "stability": 0.5,
      "similarity_boost": 0.75,
      "style": 0.0,
      "use_speaker_boost": true
    }
  },
  "default": {
    "voice_id": "pNInz6ovClqMvhaFY6HZ"
  }
}
```

Примечание: `voice_id` у `narrator`/`default` — заглушка Adam voice. Пользователь подменит перед первым реальным запуском. `default` намеренно минимален — `model_id`/`settings` подтянутся из глобальных дефолтов при `resolve_voice`.

- [ ] **Step 2: Commit**

```bash
git add voices.json
git commit -m "feat(tts): add voices.json skeleton with narrator + default"
```

---

## Task 3: `tts.py` skeleton + constants

**Files:**
- Create: `tts.py`

- [ ] **Step 1: Создать tts.py с константами и шапкой**

```python
"""ElevenLabs TTS integration. MVP: one provider, hash-based cache, atomic writes."""
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

import requests
from mutagen.mp3 import MP3

log = logging.getLogger("comic.tts")

ELEVEN_API_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_SETTINGS: dict[str, Any] = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}
MAX_CONSECUTIVE_ERRORS = 5
TTS_MAX_RETRIES = 6
TTS_REQUEST_TIMEOUT = 120  # seconds
```

- [ ] **Step 2: Smoke-импорт**

```bash
python -c "import tts; print(tts.DEFAULT_MODEL_ID)"
```
Expected: `eleven_multilingual_v2`.

- [ ] **Step 3: Commit**

```bash
git add tts.py
git commit -m "feat(tts): add tts.py skeleton with constants"
```

---

## Task 4: `load_voices` (TDD)

**Files:**
- Create: `tests/test_tts.py`
- Modify: `tts.py`

- [ ] **Step 1: Написать failing tests**

Создать `tests/test_tts.py`:
```python
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
```

- [ ] **Step 2: Запустить — должны упасть**

```bash
pytest tests/test_tts.py::TestLoadVoices -v
```
Expected: FAIL (`load_voices` не определён в `tts.py`).

- [ ] **Step 3: Имплементировать `load_voices`**

Добавить в `tts.py` после констант:
```python
def load_voices(path: Path) -> dict[str, Any]:
    """Read voices.json. Raises FileNotFoundError/ValueError on problems."""
    if not path.exists():
        raise FileNotFoundError(f"voices.json not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"voices.json is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("voices.json root must be an object")
    if "narrator" not in data:
        raise ValueError("voices.json must contain a 'narrator' entry (required fallback)")
    return data
```

- [ ] **Step 4: Запустить — должны пройти**

```bash
pytest tests/test_tts.py::TestLoadVoices -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tts.py tests/test_tts.py
git commit -m "feat(tts): load_voices with narrator validation"
```

---

## Task 5: `resolve_voice` (TDD)

**Files:**
- Modify: `tests/test_tts.py`
- Modify: `tts.py`

- [ ] **Step 1: Написать failing tests**

Добавить в `tests/test_tts.py`:
```python
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
```

- [ ] **Step 2: Запустить — должны упасть**

```bash
pytest tests/test_tts.py::TestResolveVoice -v
```
Expected: FAIL (`resolve_voice` не определён).

- [ ] **Step 3: Имплементировать `resolve_voice`**

Добавить в `tts.py`:
```python
def resolve_voice(speaker: str, voices: dict[str, Any]) -> dict[str, Any]:
    """Pick voice entry: speaker → default → narrator.
    Returns merged config {voice_id, model_id, settings}.
    Missing model_id/settings in the chosen entry fall back to module defaults.
    Raises ValueError if narrator is absent.
    """
    if "narrator" not in voices:
        raise ValueError("voices dict has no 'narrator' fallback")

    entry = voices.get(speaker) or voices.get("default") or voices["narrator"]

    voice_id = entry.get("voice_id")
    if not voice_id:
        raise ValueError(f"voice entry for {speaker!r} has no voice_id")

    return {
        "voice_id": voice_id,
        "model_id": entry.get("model_id", DEFAULT_MODEL_ID),
        "settings": entry.get("settings", DEFAULT_SETTINGS),
    }
```

- [ ] **Step 4: Тесты — зелёные**

```bash
pytest tests/test_tts.py::TestResolveVoice -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add tts.py tests/test_tts.py
git commit -m "feat(tts): resolve_voice with fallback chain speaker→default→narrator"
```

---

## Task 6: `voice_hash` (TDD)

**Files:**
- Modify: `tests/test_tts.py`
- Modify: `tts.py`

- [ ] **Step 1: Написать failing tests**

Добавить в `tests/test_tts.py`:
```python
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
```

- [ ] **Step 2: Запустить — fail**

```bash
pytest tests/test_tts.py::TestVoiceHash -v
```
Expected: FAIL (`voice_hash` не определён).

- [ ] **Step 3: Имплементировать**

Добавить в `tts.py`:
```python
def voice_hash(voice_text: str, cfg: dict[str, Any]) -> str:
    """SHA256 over text + voice_id + model_id + canonical(settings).
    sort_keys ensures reordering voices.json doesn't invalidate the cache.
    """
    blob = (
        voice_text.strip().encode("utf-8")
        + b"|" + cfg["voice_id"].encode("utf-8")
        + b"|" + cfg["model_id"].encode("utf-8")
        + b"|" + json.dumps(cfg["settings"], sort_keys=True, ensure_ascii=True).encode("utf-8")
    )
    return hashlib.sha256(blob).hexdigest()
```

- [ ] **Step 4: Зелёные**

```bash
pytest tests/test_tts.py::TestVoiceHash -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add tts.py tests/test_tts.py
git commit -m "feat(tts): voice_hash with canonical settings for stable caching"
```

---

## Task 7: `audio_duration` helper (TDD)

**Files:**
- Modify: `tests/test_tts.py`
- Modify: `tts.py`

- [ ] **Step 1: Написать failing test**

Добавить в `tests/test_tts.py`:
```python
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
```

Примечание: фикстуру `tests/fixtures/silence_1s.mp3` сгенерируем в Task 12 (smoke). Тест параметризован как skip — unit-слой не требует реального mp3.

- [ ] **Step 2: Запустить — fail (import)**

```bash
pytest tests/test_tts.py::TestAudioDuration -v
```
Expected: FAIL (`audio_duration` не определён в `tts.py`).

- [ ] **Step 3: Имплементировать**

Добавить в `tts.py`:
```python
def audio_duration(mp3_path: Path) -> float:
    """Parse mp3 duration (seconds) via mutagen."""
    return float(MP3(str(mp3_path)).info.length)
```

- [ ] **Step 4: Тест — passed (или skipped)**

```bash
pytest tests/test_tts.py::TestAudioDuration -v
```
Expected: 1 passed или 1 skipped (фикстура ещё не создана — это ок).

- [ ] **Step 5: Commit**

```bash
git add tts.py tests/test_tts.py
git commit -m "feat(tts): audio_duration via mutagen"
```

---

## Task 8: `generate_tts` (HTTP with mock tests)

**Files:**
- Modify: `tests/test_tts.py`
- Modify: `tts.py`

- [ ] **Step 1: Написать failing tests (requests-mock)**

Добавить в `tests/test_tts.py`:
```python
import requests
from tts import generate_tts, ELEVEN_API_BASE


MP3_MAGIC = b"\xff\xfb\x90\x00" + b"\x00" * 256  # minimal-ish MP3 header + padding


class TestGenerateTts:
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
```

- [ ] **Step 2: Запустить — fail**

```bash
pytest tests/test_tts.py::TestGenerateTts -v
```
Expected: FAIL (`generate_tts` не определён).

- [ ] **Step 3: Имплементировать `generate_tts`**

Добавить в `tts.py` (после `audio_duration`). Импортируем `classify_error` + `backoff_delay` из `generate_comic`:

```python
def _sleep(delay: float) -> None:
    """Indirection so tests can monkeypatch."""
    import time
    time.sleep(delay)


def generate_tts(voice_text: str, cfg: dict[str, Any], out_path: Path, api_key: str) -> None:
    """POST to ElevenLabs text-to-speech. Write mp3 atomically to out_path.

    Retries on classify_error -> rate_limit/overload/server/timeout/unknown.
    Raises RuntimeError on fatal or after TTS_MAX_RETRIES.
    """
    # Lazy import, чтобы избежать cycle при импорте tts в generate_comic
    from generate_comic import classify_error, backoff_delay

    url = f"{ELEVEN_API_BASE}/text-to-speech/{cfg['voice_id']}"
    params = {"output_format": DEFAULT_OUTPUT_FORMAT}
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    body = {
        "text": voice_text,
        "model_id": cfg["model_id"],
        "voice_settings": cfg["settings"],
    }

    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    last_err: Exception | None = None

    for attempt in range(TTS_MAX_RETRIES):
        try:
            resp = requests.post(
                url, params=params, headers=headers, json=body,
                timeout=TTS_REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path.write_bytes(resp.content)
                os.replace(tmp_path, out_path)
                return
            # Non-200 → превращаем в исключение с текстом кода, чтобы classify_error распознал
            raise RuntimeError(f"{resp.status_code} {resp.text[:200]}")
        except Exception as e:
            last_err = e
            kind, retry_after = classify_error(e)
            if kind == "fatal":
                raise RuntimeError(f"TTS fatal: {e}") from e
            if attempt == TTS_MAX_RETRIES - 1:
                break
            delay = backoff_delay(attempt, kind, retry_after=retry_after)
            log.warning("TTS retry %d/%d after %.1fs (%s): %s",
                        attempt + 1, TTS_MAX_RETRIES, delay, kind, e)
            _sleep(delay)

    # tmp мог остаться при ошибке записи — подчистим
    if tmp_path.exists():
        try:
            tmp_path.unlink()
        except OSError:
            pass
    raise RuntimeError(f"TTS retries exhausted: {last_err}")
```

- [ ] **Step 4: Отключить реальный sleep в тестах**

Дополнить `tests/test_tts.py` в начале класса `TestGenerateTts`:
```python
    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch):
        monkeypatch.setattr("tts._sleep", lambda d: None)
```

- [ ] **Step 5: Тесты — зелёные**

```bash
pytest tests/test_tts.py::TestGenerateTts -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add tts.py tests/test_tts.py
git commit -m "feat(tts): generate_tts with retry + atomic write"
```

---

## Task 9: `run_tts_stage` (TDD)

**Files:**
- Modify: `tests/test_tts.py`
- Modify: `tts.py`

- [ ] **Step 1: Написать failing tests с fake generate_tts**

Добавить в `tests/test_tts.py`:
```python
from dataclasses import dataclass, asdict, field
from tts import run_tts_stage


@dataclass
class FakeScene:
    index: int
    voice_text: str = ""
    speaker: str = "narrator"
    status: str = "ok"
    audio_path: str = ""
    audio_status: str = "pending"
    audio_hash: str = ""
    audio_duration: float = 0.0
    audio_error: str = ""


class TestRunTtsStage:
    def _voices(self):
        return {"narrator": {"voice_id": "v1"}}

    def test_skip_when_hash_matches_and_file_exists(self, tmp_path, monkeypatch):
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        scene = FakeScene(index=1, voice_text="hi", speaker="narrator")
        # Предыдущий run — hash уже проставлен и файл есть
        from tts import resolve_voice, voice_hash
        cfg = resolve_voice(scene.speaker, self._voices())
        scene.audio_hash = voice_hash(scene.voice_text, cfg)
        scene.audio_path = str(audio_dir / "scene_001.mp3")
        Path(scene.audio_path).write_bytes(b"\xff\xfb")

        # generate_tts не должен вызываться
        calls = []
        monkeypatch.setattr("tts.generate_tts", lambda *a, **kw: calls.append(a))
        monkeypatch.setattr("tts.audio_duration", lambda p: 1.0)

        summary = run_tts_stage([scene], self._voices(), "k", audio_dir,
                                 save_progress_fn=lambda: None)
        assert calls == []
        assert summary["skipped"] == 1
        assert summary["ok"] == 0

    def test_generate_and_record_duration(self, tmp_path, monkeypatch):
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        scene = FakeScene(index=2, voice_text="hello", speaker="narrator")

        def fake_gen(text, cfg, out_path, api_key):
            out_path.write_bytes(b"\xff\xfb")
        monkeypatch.setattr("tts.generate_tts", fake_gen)
        monkeypatch.setattr("tts.audio_duration", lambda p: 2.5)

        summary = run_tts_stage([scene], self._voices(), "k", audio_dir,
                                 save_progress_fn=lambda: None)
        assert summary["ok"] == 1
        assert scene.audio_status == "ok"
        assert scene.audio_duration == 2.5
        assert scene.audio_hash  # non-empty

    def test_empty_voice_text_skipped(self, tmp_path, monkeypatch):
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        scene = FakeScene(index=3, voice_text="", speaker="narrator")
        monkeypatch.setattr("tts.generate_tts", lambda *a, **kw: None)
        summary = run_tts_stage([scene], self._voices(), "k", audio_dir,
                                 save_progress_fn=lambda: None)
        assert summary["skipped"] == 1
        assert scene.audio_status == "skipped"

    def test_consecutive_errors_abort(self, tmp_path, monkeypatch):
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        scenes = [FakeScene(index=i, voice_text=f"t{i}", speaker="narrator")
                  for i in range(1, 8)]

        def fake_gen(text, cfg, out_path, api_key):
            raise RuntimeError("TTS fatal: 401 unauthorized")
        monkeypatch.setattr("tts.generate_tts", fake_gen)

        summary = run_tts_stage(scenes, self._voices(), "k", audio_dir,
                                 save_progress_fn=lambda: None)
        assert summary["aborted"] is True
        assert summary["error"] == 5  # MAX_CONSECUTIVE_ERRORS
        # Сцены после abort остались pending
        assert scenes[5].audio_status == "pending"
        assert scenes[6].audio_status == "pending"

    def test_error_counter_resets_on_success(self, tmp_path, monkeypatch):
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        scenes = [FakeScene(index=i, voice_text=f"t{i}", speaker="narrator")
                  for i in range(1, 8)]

        # Паттерн: 4 ошибки, успех, 4 ошибки — счётчик должен сброситься
        call_count = {"n": 0}
        def fake_gen(text, cfg, out_path, api_key):
            call_count["n"] += 1
            if call_count["n"] == 5:
                out_path.write_bytes(b"\xff\xfb")
                return
            raise RuntimeError("TTS fatal: 400 bad request")
        monkeypatch.setattr("tts.generate_tts", fake_gen)
        monkeypatch.setattr("tts.audio_duration", lambda p: 1.0)

        summary = run_tts_stage(scenes, self._voices(), "k", audio_dir,
                                 save_progress_fn=lambda: None)
        # Abort случится после 5 ошибок подряд (начиная со сцены 6, после успеха на сцене 5)
        # Фактически: err err err err ok err err err => три ошибки, abort НЕ должен сработать
        assert summary["aborted"] is False
```

- [ ] **Step 2: Запустить — fail**

```bash
pytest tests/test_tts.py::TestRunTtsStage -v
```
Expected: FAIL (`run_tts_stage` не определён).

- [ ] **Step 3: Имплементировать `run_tts_stage`**

Добавить в `tts.py`:
```python
def run_tts_stage(
    scenes: list[Any],
    voices: dict[str, Any],
    api_key: str,
    audio_dir: Path,
    save_progress_fn: Callable[[], None],
) -> dict[str, Any]:
    """Generate audio for scenes with status=='ok' and non-empty voice_text.

    Writes audio to audio_dir/scene_NNN.mp3. Updates scene fields in place:
    audio_path, audio_status, audio_hash, audio_duration, audio_error.

    Skips scenes whose hash matches and file already exists.
    Aborts stage when MAX_CONSECUTIVE_ERRORS hit in a row.

    Returns summary dict {ok, skipped, error, aborted}.
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    summary = {"ok": 0, "skipped": 0, "error": 0, "aborted": False}
    consecutive_errors = 0

    for scene in scenes:
        # Только успешно отрендеренные / dry-run-ok сцены с текстом для TTS
        if scene.status != "ok":
            continue
        if not scene.voice_text:
            scene.audio_status = "skipped"
            summary["skipped"] += 1
            save_progress_fn()
            continue

        try:
            cfg = resolve_voice(scene.speaker, voices)
        except ValueError as e:
            scene.audio_status = "error"
            scene.audio_error = f"resolve_voice failed: {e}"
            summary["error"] += 1
            consecutive_errors += 1
            save_progress_fn()
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log.error("TTS: %d consecutive errors, aborting stage", consecutive_errors)
                summary["aborted"] = True
                return summary
            continue

        h = voice_hash(scene.voice_text, cfg)
        out_path = audio_dir / f"scene_{scene.index:03d}.mp3"

        # Cache hit?
        if scene.audio_hash == h and out_path.exists():
            scene.audio_path = str(out_path)
            # Обновим duration на всякий случай (если раньше не сохранили)
            if not scene.audio_duration:
                try:
                    scene.audio_duration = audio_duration(out_path)
                except Exception as e:
                    log.warning("audio_duration read failed for %s: %s", out_path, e)
            summary["skipped"] += 1
            consecutive_errors = 0
            save_progress_fn()
            continue

        # Generate
        try:
            generate_tts(scene.voice_text, cfg, out_path, api_key)
            scene.audio_path = str(out_path)
            scene.audio_hash = h
            scene.audio_status = "ok"
            scene.audio_error = ""
            try:
                scene.audio_duration = audio_duration(out_path)
            except Exception as e:
                log.warning("audio_duration read failed for scene %d: %s", scene.index, e)
                scene.audio_duration = 0.0
            summary["ok"] += 1
            consecutive_errors = 0
        except Exception as e:
            scene.audio_status = "error"
            scene.audio_error = str(e)[:500]
            summary["error"] += 1
            consecutive_errors += 1
            log.error("TTS scene %d failed: %s", scene.index, e)
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log.error("TTS: %d consecutive errors, aborting stage", consecutive_errors)
                summary["aborted"] = True
                save_progress_fn()
                return summary
        finally:
            save_progress_fn()

    return summary
```

- [ ] **Step 4: Тесты — зелёные**

```bash
pytest tests/test_tts.py::TestRunTtsStage -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tts.py tests/test_tts.py
git commit -m "feat(tts): run_tts_stage with hash cache + consecutive abort"
```

---

## Task 10: `Scene` dataclass — новые поля

**Files:**
- Modify: `generate_comic.py:115-132`

- [ ] **Step 1: Добавить audio-поля в Scene**

Заменить блок `Scene` (строки 115-132) на:

```python
@dataclass
class Scene:
    index: int
    text: str                           # original Russian excerpt
    title: str = ""                     # short label from LLM
    character_ids: list[str] = field(default_factory=list)
    prompt: str = ""                    # final English prompt for image model
    status: str = "pending"             # pending | ok | skipped | error
    error: str = ""
    image_path: str = ""
    model_used: str = ""
    # Voice / subtitles metadata (filled by scene LLM pass)
    voice_text: str = ""                # clean RU text for TTS
    speaker: str = "narrator"           # "narrator" | <character_id>
    emotion: str = ""                   # e.g. "melancholic", "tense"
    pacing: str = "normal"              # "slow" | "normal" | "fast"
    duration_sec: float = 0.0           # estimated clip length
    subtitle_lines: list[str] = field(default_factory=list)
    # TTS metadata (filled by run_tts_stage)
    audio_path: str = ""
    audio_status: str = "pending"       # pending | ok | skipped | error
    audio_hash: str = ""
    audio_duration: float = 0.0
    audio_error: str = ""
```

- [ ] **Step 2: Проверить что старые тесты не сломались**

```bash
pytest tests/test_pure.py tests/test_schemas.py tests/test_tts.py -v
```
Expected: все старые + новые TTS passed.

- [ ] **Step 3: Проверить что старый progress.json читается**

Новые поля имеют дефолты → старые файлы без них должны загружаться. Быстрая проверка:
```bash
python -c "from dataclasses import asdict; from generate_comic import Scene; s = Scene(index=1, text='x'); print(asdict(s))"
```
Expected: dict содержит `audio_status='pending'`, `audio_duration=0.0`.

- [ ] **Step 4: Commit**

```bash
git add generate_comic.py
git commit -m "feat(tts): Scene dataclass audio fields"
```

---

## Task 11: `effective_duration` + `export_srt` использует реальную длительность

**Files:**
- Modify: `generate_comic.py:789-828`
- Modify: `tests/test_pure.py`

- [ ] **Step 1: Написать failing test**

Добавить в конец `tests/test_pure.py`:
```python
from generate_comic import effective_duration, Scene


class TestEffectiveDuration:
    def test_uses_audio_duration_when_present(self):
        s = Scene(index=1, text="x", voice_text="hello", audio_duration=3.5)
        assert effective_duration(s) == 3.5

    def test_fallback_when_audio_duration_zero(self):
        s = Scene(index=1, text="x", voice_text="hello", audio_duration=0.0)
        # fallback идёт в estimate_duration → > MIN_SCENE_DURATION
        assert effective_duration(s) >= MIN_SCENE_DURATION

    def test_fallback_when_no_voice_text(self):
        s = Scene(index=1, text="fallback text", voice_text="")
        # estimate_duration на scene.text
        assert effective_duration(s) >= MIN_SCENE_DURATION

    def test_audio_duration_wins_even_if_duration_sec_set(self):
        s = Scene(index=1, text="x", voice_text="hello",
                  duration_sec=10.0, audio_duration=2.2)
        assert effective_duration(s) == 2.2
```

- [ ] **Step 2: Запустить — fail**

```bash
pytest tests/test_pure.py::TestEffectiveDuration -v
```
Expected: FAIL (`effective_duration` не определена).

- [ ] **Step 3: Имплементировать + интегрировать в export_srt**

В `generate_comic.py`, **перед** `def export_srt(...)` (строка 807), добавить:

```python
def effective_duration(scene: "Scene") -> float:
    """Prefer real audio duration from TTS; fallback to estimate.

    Priority:
    1. audio_duration (set by run_tts_stage)
    2. duration_sec (legacy precomputed estimate)
    3. estimate_duration(voice_text or text, pacing)
    """
    if scene.audio_duration and scene.audio_duration > 0:
        return float(scene.audio_duration)
    if scene.duration_sec and scene.duration_sec > 0:
        return float(scene.duration_sec)
    return estimate_duration(scene.voice_text or scene.text, scene.pacing)
```

Заменить блок внутри `export_srt` (строки 815-816) со старого:
```python
        dur = scene.duration_sec or estimate_duration(
            scene.voice_text or scene.text, scene.pacing)
```
на:
```python
        dur = effective_duration(scene)
```

- [ ] **Step 4: Тесты — зелёные**

```bash
pytest tests/test_pure.py -v
```
Expected: все passed, включая новые 4 для `effective_duration`.

- [ ] **Step 5: Commit**

```bash
git add generate_comic.py tests/test_pure.py
git commit -m "feat(tts): effective_duration prefers real audio over estimate in SRT"
```

---

## Task 12: CLI аргументы + интеграция TTS-этапа в main()

**Files:**
- Modify: `generate_comic.py:835-1085`

- [ ] **Step 1: Добавить CLI-аргументы**

В `main()` после `ap.add_argument("--verbose", ...)` (строка 857) добавить:

```python
    ap.add_argument("--tts", action="store_true",
                    help="Generate TTS audio via ElevenLabs after images")
    ap.add_argument("--tts-only", action="store_true",
                    help="Skip image stage; (re)generate audio + SRT from existing progress.json")
    ap.add_argument("--voices", default="voices.json", type=Path,
                    help="Path to voices.json mapping speakers to ElevenLabs voice configs")
```

- [ ] **Step 2: Добавить импорт tts и preflight**

В шапке `generate_comic.py` среди импортов (после `import argparse, os, sys, ...`) добавить:
```python
import tts as tts_mod
```

В `main()` после блока проверки `GEMINI_API_KEY` (строка 869), добавить:
```python
    if args.tts or args.tts_only:
        eleven_key = os.environ.get("ELEVEN_API_KEY")
        if not eleven_key:
            sys.exit("ERROR: ELEVEN_API_KEY not set in .env, required for --tts")
        voices_path = args.voices
        if not voices_path.exists():
            sys.exit(f"ERROR: {voices_path} not found (required for --tts)")
        try:
            voices = tts_mod.load_voices(voices_path)
        except (ValueError, FileNotFoundError) as e:
            sys.exit(f"ERROR: {e}")
    else:
        eleven_key = None
        voices = None
```

- [ ] **Step 3: Вставить TTS-stage после image loop**

Найти блок `# ── Write final prompts.json ──` (строка 1067). **Перед** ним, но **после** главного `for scene in scenes:` loop, добавить:

```python
    # ── TTS stage ────────────────────────────────────────────────────────
    if args.tts or args.tts_only:
        audio_dir = out_dir / "audio"
        log.info("TTS stage: ElevenLabs → %s", audio_dir)
        tts_summary = tts_mod.run_tts_stage(
            scenes=scenes,
            voices=voices,
            api_key=eleven_key,
            audio_dir=audio_dir,
            save_progress_fn=lambda: save_progress(progress_path, scenes),
        )
        log.info("TTS: %d ok, %d skipped, %d error%s",
                 tts_summary["ok"], tts_summary["skipped"],
                 tts_summary["error"],
                 " (ABORTED)" if tts_summary["aborted"] else "")
```

- [ ] **Step 4: Smoke — dry-run с --tts**

```bash
python generate_comic.py --story story.txt --batch --dry-run --tts --limit 1
```
Expected:
- preflight ok (нашёл `voices.json`, `ELEVEN_API_KEY`);
- TTS-stage вызвался;
- реальный HTTP-запрос сделан, mp3 сохранён в `output/audio/scene_001.mp3`;
- `progress.json` содержит `audio_status=ok`, `audio_hash`, `audio_duration`.

Если провайдер/ключ не готов — проверить что preflight падает с понятной ошибкой:
```bash
ELEVEN_API_KEY="" python generate_comic.py --story story.txt --tts
# ожидаемо: ERROR: ELEVEN_API_KEY not set in .env, required for --tts
```

- [ ] **Step 5: Commit**

```bash
git add generate_comic.py
git commit -m "feat(tts): --tts CLI flag + run_tts_stage integration in main"
```

---

## Task 13: `--tts-only` standalone-путь

**Files:**
- Modify: `generate_comic.py:main`

- [ ] **Step 1: Рефакторинг main() под early-exit для --tts-only**

В `main()`, сразу после обработки `voices` (шаг конца Task 12), добавить ветку:

```python
    if args.tts_only:
        # Ранний путь: ждём уже сгенерированные картинки + prompts.json
        if not progress_path.exists():
            sys.exit(f"ERROR: --tts-only requires existing {progress_path}")
        data = json.loads(progress_path.read_text(encoding="utf-8"))
        scenes = [Scene(**s) for s in data["scenes"]]

        audio_dir = out_dir / "audio"
        log.info("TTS-only stage: ElevenLabs → %s", audio_dir)
        tts_summary = tts_mod.run_tts_stage(
            scenes=scenes, voices=voices, api_key=eleven_key,
            audio_dir=audio_dir,
            save_progress_fn=lambda: save_progress(progress_path, scenes),
        )
        log.info("TTS: %d ok, %d skipped, %d error%s",
                 tts_summary["ok"], tts_summary["skipped"],
                 tts_summary["error"],
                 " (ABORTED)" if tts_summary["aborted"] else "")

        # Regenerate SRT с новой длительностью
        try:
            export_srt(scenes, srt_path)
        except Exception as e:
            log.warning("SRT export failed: %s", e)

        log.info("Done (tts-only).")
        return
```

**Важно:** ветку добавить ДО строки `story = Path(args.story).read_text(...)`, чтобы `--tts-only` не падал когда `story.txt` отсутствует (хотя обычно он есть).

**НО:** `args.story` required=True в argparse. Чтобы `--tts-only` работал без `story`, изменить:
```python
ap.add_argument("--story", required=False, default=None,
                help="Path to story.txt (required unless --tts-only)")
```

И добавить проверку:
```python
    if not args.tts_only and not args.story:
        sys.exit("ERROR: --story required unless --tts-only is set")
```

- [ ] **Step 2: Smoke-тест --tts-only на существующем output/**

Предварительно: должен быть готовый `output/progress.json` от предыдущего run'а.
```bash
python generate_comic.py --tts-only
```
Expected:
- скрипт не требует `--story`;
- загружает scenes из progress;
- вызывает TTS; если кэш валиден — все сцены skipped;
- SRT перезаписан.

Повторный ран:
```bash
python generate_comic.py --tts-only
```
Expected: `N ok → N skipped`, никаких реальных HTTP-вызовов (проверить в `--verbose`).

- [ ] **Step 3: Commit**

```bash
git add generate_comic.py
git commit -m "feat(tts): --tts-only standalone stage skipping image gen"
```

---

## Task 14: Fixture + smoke duration round-trip

**Files:**
- Create: `tests/fixtures/silence_1s.mp3`
- Modify: `tests/test_tts.py`

- [ ] **Step 1: Сгенерить короткий mp3**

Вариант A (есть ffmpeg):
```bash
mkdir -p tests/fixtures
ffmpeg -f lavfi -i "anullsrc=r=44100:cl=mono" -t 1 -b:a 128k tests/fixtures/silence_1s.mp3 -y
```

Вариант B (нет ffmpeg) — пропустить, тест `test_reads_real_mp3` останется skipped. НЕ блокирует merge.

- [ ] **Step 2: Прогнать audio_duration тест**

```bash
pytest tests/test_tts.py::TestAudioDuration -v
```
Expected: 1 passed (если fixture есть) или skipped.

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/silence_1s.mp3
git commit -m "test(tts): add 1s silence mp3 fixture for duration tests"
```

Если fixture не создавалась — шаги 2 и 3 пропустить.

---

## Task 15: Обновить docs (README, TODO, CLAUDE.md)

**Files:**
- Modify: `README.md`
- Modify: `TODO.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: README — новый раздел про TTS**

В `README.md` добавить после раздела про пайплайн новый раздел:

```markdown
## TTS-озвучка (ElevenLabs)

Пайплайн умеет автоматически озвучивать сцены через ElevenLabs.

### Настройка
1. Получить API-ключ на https://elevenlabs.io/app/settings/api-keys
2. Добавить в `.env`:
   ```
   ELEVEN_API_KEY=your-key-here
   ```
3. Отредактировать `voices.json` — прописать `voice_id` для narrator'а и персонажей.
   Voice_id берётся из Voice Library или из URL голоса на сайте ElevenLabs.

### Запуск
```bash
# Полный пайплайн + TTS
python generate_comic.py --story story.txt --batch --tts

# Только TTS по готовому output/ (без пересбора картинок)
python generate_comic.py --tts-only
```

После — `output/audio/scene_NNN.mp3` рядом с кадрами, `subtitles.srt` с точной длительностью.

### Кэш
Каждая сцена хешируется (text + voice_id + model + settings). Повторный запуск пропускает всё неизменённое. Меняешь голос в `voices.json` — автоматическая перегенерация.

### Ошибки
- Сбой провайдера на одной сцене → `audio_status=error`, остальные продолжают.
- 5 ошибок подряд → stage aborted, остальные сцены остаются `pending`, перезапусти позже.
```

- [ ] **Step 2: TODO.md — вычеркнуть сделанное**

В `TODO.md`, раздел 2 «TTS-интеграция», заменить:
```markdown
- 🔴 **`--tts elevenlabs|yandex|silero`** — флаг для выбора движка.
- 🔴 **Маппинг speaker → voice_id** в новом `voices.json` (аналог `characters.json`):
```
на:
```markdown
- ✅ **`--tts`** — флаг генерации через ElevenLabs (апрель 2026). Yandex/Silero — следующие итерации.
- ✅ **Маппинг speaker → voice_id** в `voices.json` с fallback-цепочкой `speaker → default → narrator`.
- ✅ **Сохранение аудио** в `output/audio/scene_NNN.mp3` с атомарной записью.
- ✅ **Кэш TTS** по hash(text + voice_id + model + settings) — per-scene в progress.json.
- 🟡 **Учёт emotion/pacing** в настройках TTS — не закрыт (текущая реализация берёт static settings).
- 🟡 **Нормализация аудио** (ffmpeg loudnorm) — не закрыт (ждёт `--render-video`).
- 🟢 **Yandex SpeechKit** — следующий подпроект, потребует provider abstraction.
- 🟢 **Silero** — локальный fallback, следующий подпроект.
```

В разделе «Приоритеты: что делать первым», обновить пункт 1:
```markdown
1. ✅ **TTS-интеграция** (пункт 2) — ElevenLabs end-to-end готов (апрель 2026).
```

- [ ] **Step 3: CLAUDE.md — обновить архитектуру + статус**

В секции «Архитектура», в ASCII-диаграмме после `image gen` добавить:
```
       ├─ TTS stage ────────► output/audio/scene_*.mp3 (ElevenLabs, --tts)
```

В таблице «Главные функции» добавить строку:
```
| `effective_duration` | ~805 | SRT prefers real mp3 duration over estimate |
```

В секции «Статус», переместить из «В работе» в «Готово»:
```markdown
- **TTS-интеграция (ElevenLabs)** — `--tts`, `--tts-only`, `voices.json`, hash-cache, SRT по реальной длительности.
```

В «В работе (апрель 2026)» обновить:
```markdown
Нет активных подпроектов. Следующий — `--render-video` (TODO раздел 3).
```

В Roadmap пункт 1 пометить галочкой:
```markdown
1. ✅ **TTS-интеграция** (TODO раздел 2) — апрель 2026.
2. **`--render-video`** (TODO раздел 3): финальная ffmpeg-склейка кадров + голоса + SRT → mp4
```

- [ ] **Step 4: Commit**

```bash
git add README.md TODO.md CLAUDE.md
git commit -m "docs(tts): document --tts flow, mark TODO items done"
```

---

## Task 16: End-to-end smoke + финальная проверка

- [ ] **Step 1: Прогнать полный тест-сьют**

```bash
pytest tests/ -v
```
Expected: all passed.

- [ ] **Step 2: End-to-end smoke на 1 сцене с реальным API**

```bash
python generate_comic.py --story story.txt --bootstrap --batch --tts --limit 1 --verbose
```
Expected:
- сцена 1 получает картинку + mp3;
- `output/audio/scene_001.mp3` воспроизводится вручную (проверка качества голоса);
- `output/subtitles.srt` — длительность первой cue совпадает с mp3 в пределах ±0.1с;
- `output/progress.json` содержит полный набор audio-полей.

- [ ] **Step 3: Idempotency check**

Повторный запуск той же команды:
```bash
python generate_comic.py --story story.txt --batch --tts --limit 1 --verbose
```
Expected: TTS-stage лог `1 skipped, 0 ok` — кэш сработал.

- [ ] **Step 4: --tts-only smoke**

```bash
python generate_comic.py --tts-only --limit 1 --verbose
```
Expected: картинки не трогаются, TTS либо skip (кэш hit) либо regenerate, SRT перезаписан.

- [ ] **Step 5: Merge в master**

```bash
git log --oneline master..feature/tts-integration
# ожидаем чистую серию коммитов feat(tts)/chore(tts)/test(tts)/docs(tts)

git checkout master
git merge --no-ff feature/tts-integration -m "Merge feature/tts-integration: ElevenLabs TTS end-to-end"
```

---

## Self-Review (сделано)

**Spec coverage:**
- Раздел 2 (Architecture) → Task 12, 13.
- Раздел 3 (voices.json, progress fields, hash) → Task 2, 6, 10.
- Раздел 4 (tts.py API) → Task 3–9.
- Раздел 5 (error handling) → Task 8 (retry), Task 9 (consecutive abort), Task 12 (preflight).
- Раздел 6 (SRT integration) → Task 11.
- Раздел 7 (testing) → Task 4–9, 11, 14, 16.
- Раздел 8 (dependencies) → Task 1.
- Раздел 9 (изменения в других файлах) → Task 1, 10, 11, 15.

**Placeholder scan:** Нет TBD/TODO/placeholder шагов. Все test cases и код — полные.

**Type consistency:**
- `run_tts_stage(scenes, voices, api_key, audio_dir, save_progress_fn)` — одинаково в spec/plan/code.
- `voice_hash(text, cfg)` / `resolve_voice(speaker, voices)` / `generate_tts(text, cfg, out_path, api_key)` — сигнатуры совпадают во всех задачах.
- `audio_status` значения (`pending|ok|skipped|error`) — одинаковые везде.
- Scene new fields (`audio_path/audio_status/audio_hash/audio_duration/audio_error`) — упоминаются согласованно.
