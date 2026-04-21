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


def audio_duration(mp3_path: Path) -> float:
    """Parse mp3 duration (seconds) via mutagen."""
    return float(MP3(str(mp3_path)).info.length)


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
