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
