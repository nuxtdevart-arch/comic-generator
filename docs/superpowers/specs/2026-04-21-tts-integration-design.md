# TTS Integration — Design

**Дата:** 2026-04-21
**Scope:** TODO раздел 2 — автоматическая генерация озвучки сцен через ElevenLabs.
**Статус:** Approved, готов к плану реализации.

---

## 1. Цель

Убрать ручную работу по превращению `voice_text` сцен в аудиофайлы. После `--tts` рядом с кадрами лежат `output/audio/scene_NNN.mp3`, SRT-тайминги совпадают с реальной длительностью озвучки.

### Ненужное для этой итерации (YAGNI)
- Yandex SpeechKit, Silero — отдельные подпроекты позже.
- Эмоциональные/темповые настройки TTS из `emotion`/`pacing` сцены — текст уже интонирован LLM.
- Inline `[emotion]` теги ElevenLabs v3 — alpha, нестабильно.
- Нормализация громкости (`ffmpeg loudnorm`), bgm, ducking — задачи этапа `--render-video`.
- Provider-абстракция — появится, когда зайдёт второй провайдер. Сейчас гадать интерфейс слепо.

---

## 2. Архитектура

```
image gen stage (existing) ──► output/frame_NNN.png  + progress.json
                                      │
                                      ▼
TTS stage (NEW, gated by --tts) ──► output/audio/scene_NNN.mp3
                                      │
                                      ▼
SRT export stage (existing, modified) ──► output/subtitles.srt
```

### Ключевые свойства
- TTS — **отдельный этап** между image gen и SRT. При сбое провайдера картинки не блокируются.
- Флаг **`--tts-only`** — standalone-режим: по готовому `prompts.json`/`progress.json` догенерирует аудио + SRT, картинки не трогает.
- Хеш-кэш per-сцена: `voice_text + voice_id + model_id + settings` → SHA256. Повторный запуск — skip неизменённых. Меняешь голос в `voices.json` → автоматическая перегенерация.
- Skip-and-continue при ошибках, fail-fast при 5 fatal подряд.
- SRT использует **реальную длительность mp3** когда она есть, иначе fallback на `estimate_duration`.

### Новый модуль
`tts.py` на корне проекта, рядом с `generate_comic.py`. Весь TTS-код (HTTP, caching, duration parsing, stage runner) живёт здесь. `generate_comic.py` импортирует и вызывает. Причина: монолит уже ~1050 строк, новая фича с чёткой границей — не раздувать дальше. Вынос утилит (`classify_error`, `backoff_delay`) в общий модуль отложен до раздела 9 roadmap.

---

## 3. Данные

### 3.1 `voices.json` (новый, на корне)

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
    "voice_id": "...",
    "model_id": "eleven_multilingual_v2",
    "settings": { "stability": 0.5, "similarity_boost": 0.75 }
  },
  "aleksey_38": {
    "voice_id": "..."
  }
}
```

Правила:
- `narrator` — **обязательная** запись (последний fallback, используется и для самого рассказчика).
- `default` — опциональная (промежуточный fallback для unknown speaker).
- Персонажные записи — опциональные, могут опускать `model_id` и `settings` (merge с глобальными дефолтами `DEFAULT_MODEL_ID`, `DEFAULT_SETTINGS`).

### 3.2 Новые поля в `progress.json` per-scene

```json
{
  "scene_index": 5,
  "image_path": "output/frame_005.png",
  "status": "ok",
  "audio_path": "output/audio/scene_005.mp3",
  "audio_status": "ok",
  "audio_hash": "<sha256>",
  "audio_duration": 4.812,
  "audio_error": null
}
```

Значения `audio_status`: `pending` | `ok` | `error` | `skipped`.
- `skipped` — сцена без `voice_text` (если встретится).
- `error` — все retry исчерпаны или fatal.
- `audio_error` — текст последней ошибки, чтобы пользователь видел причину в `--status`-сводке.

### 3.3 Hash формула

```python
hashlib.sha256(
    voice_text.strip().encode("utf-8")
    + b"|"
    + voice_id.encode()
    + b"|"
    + model_id.encode()
    + b"|"
    + json.dumps(settings, sort_keys=True, ensure_ascii=True).encode()
).hexdigest()
```

Канонизация через `sort_keys=True` — reorder ключей в `voices.json` не инвалидирует кэш.

---

## 4. Модуль `tts.py` — API

```python
# tts.py

from pathlib import Path
import hashlib, json, logging, os, time
import requests
from mutagen.mp3 import MP3

log = logging.getLogger("comic.tts")

ELEVEN_API_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_SETTINGS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}
MAX_CONSECUTIVE_ERRORS = 5
TTS_MAX_RETRIES = 6


def load_voices(path: Path) -> dict:
    """Читает voices.json. Raises если нет narrator или JSON невалиден."""

def resolve_voice(speaker: str, voices: dict) -> dict:
    """speaker → default → narrator. Возвращает merged {voice_id, model_id, settings}.
    Raises если narrator отсутствует (защита — load_voices уже валидирует, но
    resolve может вызываться отдельно)."""

def voice_hash(voice_text: str, cfg: dict) -> str:
    """sha256(text|voice_id|model_id|canonical(settings))."""

def generate_tts(voice_text: str, cfg: dict, out_path: Path, api_key: str) -> None:
    """POST /v1/text-to-speech/{voice_id}?output_format=mp3_44100_128.
    Body: {"text": voice_text, "model_id": cfg["model_id"], "voice_settings": cfg["settings"]}.
    Retry через classify_error + backoff_delay (импорт из generate_comic).
    Пишем в {out_path}.tmp, затем os.replace → {out_path} (атомарно)."""

def audio_duration(mp3_path: Path) -> float:
    """MP3(str(mp3_path)).info.length."""

def run_tts_stage(progress: dict, voices: dict, api_key: str,
                  audio_dir: Path, save_progress_fn) -> dict:
    """Итерация по сценам. Summary: {"ok": N, "skipped": N, "error": N, "aborted": bool}."""
```

### CLI изменения в `generate_comic.py`

```python
parser.add_argument("--tts", action="store_true",
                    help="Generate TTS audio via ElevenLabs")
parser.add_argument("--tts-only", action="store_true",
                    help="Skip image stage, only (re)generate audio + SRT from existing progress.json")
parser.add_argument("--voices", default="voices.json", type=Path)
```

Взаимоисключения: `--tts-only` подразумевает `--tts` и пропускает image stage. Если `--tts-only` без `prompts.json`/`progress.json` → fail-fast.

---

## 5. Error handling

### Классификация
Переиспользуем существующий `classify_error` из `generate_comic.py` (паттерны по тексту исключения `requests` — `429`, `503`, `5xx`, `401`, `timeout`).

| Класс | Retry | Cap |
|---|---|---|
| `rate_limit` (429) | да | 300с |
| `overload` / `server` (5xx) | да | 300с |
| `timeout` | да | 120с |
| `fatal` (401/403/400, voice_id not found) | нет | — |
| `unknown` | да | 120с |

### Consecutive error abort
Глобальный счётчик в `run_tts_stage`:
- Растёт на `fatal` или после исчерпания всех retry.
- Обнуляется при успехе.
- `>= MAX_CONSECUTIVE_ERRORS (5)` → abort stage (`log.error("provider appears down, aborting")`, summary с `aborted=True`). Уже сгенерированные сцены сохранены.

### Preflight checks (до первого HTTP-вызова)
- Отсутствует `ELEVEN_API_KEY` → fail-fast: `ELEVEN_API_KEY not set in .env, required for --tts`.
- Отсутствует `voices.json` → fail-fast.
- `voices.json` без `narrator` → fail-fast.
- `voices.json` malformed JSON → fail-fast с позицией ошибки.

### Per-scene поведение
- Speaker не в `voices.json`, нет `default`, есть `narrator` → fallback на narrator + per-scene warning (не error).
- Scene без `voice_text` → `audio_status=skipped`, не вызываем API.
- Успех → атомарная запись (`.tmp` → rename), `audio_duration` из mutagen, `audio_hash` сохранён.

### Git ignore
`output/audio/*.mp3` — добавить в `.gitignore` (по аналогии с `output/frame_*.png`).

---

## 6. SRT integration

### Изменения в `generate_comic.py`

Новая вспомогательная функция:
```python
def effective_duration(scene_progress: dict) -> float:
    d = scene_progress.get("audio_duration")
    if d and d > 0:
        return float(d)
    return estimate_duration(
        scene_progress["voice_text"],
        scene_progress.get("pacing", "normal"),
    )
```

`export_srt` использует `effective_duration` вместо прямого вызова `estimate_duration`.

### Инварианты
- Без `--tts` → `audio_duration` отсутствует у всех сцен → SRT как раньше. Regression-safe.
- `--tts` сработал частично → ok-сцены имеют реальный duration, error-сцены падают на estimate. SRT валидный, тайминги error-сцен менее точные.
- Сумма длительностей = длина будущего видео ±погрешность estimate на error-сценах.

---

## 7. Тесты

### Unit-тесты (`tests/test_tts.py`, без реального API)

1. `voice_hash`:
   - Детерминизм на одинаковых входах.
   - Reorder ключей `settings` → тот же hash (canonical JSON).
   - Изменение любого поля (text/voice_id/model_id/любой setting) → другой hash.
2. `resolve_voice`:
   - Speaker есть → его конфиг.
   - Speaker нет, `default` есть → default.
   - Speaker нет, `default` нет, `narrator` есть → narrator.
   - `narrator` отсутствует → raises.
   - Merge: voice без `model_id` → подтягивает `DEFAULT_MODEL_ID`.
3. `effective_duration` (в `generate_comic.py` или `tests/test_pure.py`):
   - `audio_duration > 0` → возвращает его.
   - `audio_duration=None` / отсутствует / `0` → fallback на `estimate_duration`.
4. `load_voices`:
   - Malformed JSON → ясная ошибка.
   - Нет `narrator` → raises.

### HTTP mock (`requests-mock` или `monkeypatch`)

5. `generate_tts` happy path: mock 200 + mp3 bytes → файл записан атомарно, `.tmp` удалён.
6. `generate_tts` на 429 → retry → success.
7. `generate_tts` на 401 → fatal, raises без retry.
8. `generate_tts` прерывание во время записи → `.tmp` остаётся, финальный файл не создан (ручная проверка логики, не обязательный тест).

### Integration-ish (фейковый `generate_tts`)

9. `run_tts_stage`:
   - Skip если hash совпал и файл существует.
   - Consecutive-error abort на 5 подряд fatal.
   - Summary корректный (ok/skipped/error/aborted).

### Out of scope
- Реальные вызовы ElevenLabs в CI.
- Golden audio test (бинарное сравнение mp3 хрупко).
- Автоматическая оценка качества голоса.

### Smoke-проверка вручную
```bash
python generate_comic.py --story story.txt --batch --tts --limit 1
```
- mp3 играется.
- `progress.json` содержит `audio_hash`, `audio_duration`, `audio_status=ok`.
- SRT `scene 1` совпадает по длине с реальным mp3.

---

## 8. Зависимости

Новые пакеты:
- `requests` — уже есть (через transitive), но зафиксируем явно.
- `mutagen>=1.47` — парсинг длительности mp3.

Добавить в `requirements.txt`. Dev-зависимость `requests-mock` (опционально) — в `requirements-dev.txt`.

Переменные окружения:
- `ELEVEN_API_KEY` в `.env` — проверка при `--tts`.

---

## 9. Изменения в других файлах

- `generate_comic.py` — CLI флаги, вызов `run_tts_stage`, замена прямого `estimate_duration` на `effective_duration` в `export_srt`.
- `.gitignore` — `output/audio/`.
- `README.md` — раздел про `--tts`, пример `voices.json`, инструкция получения API-ключа.
- `TODO.md` — вычеркнуть пункты раздела 2, которые закрыли (`--tts elevenlabs`, `voices.json`, `output/audio/`, кэш TTS). Yandex/Silero/нормализация остаются.
- `CLAUDE.md` — обновить секции «Архитектура» (добавить TTS stage) и «Статус» (готово: TTS).

---

## 10. Out of scope — следующие подпроекты

- Yandex SpeechKit провайдер + provider abstraction (когда появится второй живой).
- Silero локальный fallback.
- Emotion/pacing → TTS settings маппинг.
- Audio loudness normalization (`ffmpeg loudnorm`).
- Word-level timestamps через Whisper для SRT точности.
- `--render-video` — отдельный подпроект, в нём ffmpeg уже будет.
