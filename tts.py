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
