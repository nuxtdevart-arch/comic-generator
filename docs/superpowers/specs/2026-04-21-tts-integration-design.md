# TTS Integration — Design

**Date:** 2026-04-21
**Scope:** TODO.md раздел 2 — интеграция с внешними TTS-провайдерами.
**Status:** Draft.

---

## 1. Goal

Автоматизировать генерацию озвучки для каждой сцены, чтобы исключить ручной труд по превращению `voice_text` в аудиофайлы.

**Основные требования:**
1. Поддержка провайдеров: ElevenLabs (основной), Yandex SpeechKit, Silero (локальный).
2. Маппинг персонажей на голоса через `voices.json`.
3. Сохранение аудио в `output/audio/scene_XXX.mp3`.
4. Интеграция в основной пайплайн через флаг `--tts <provider>`.
5. Кэширование (не генерировать, если текст и голос не изменились).
6. Обработка ошибок и ретраи (429/5xx).

---

## 2. Architecture

### 2.1 Новые файлы
- `voices.json` — конфигурация голосов.
- `comic/tts.py` — (в будущем при рефакторинге, пока в `generate_comic.py` или отдельном модуле). *Решение:* Для соответствия текущему стилю проекта (монолит), добавим функции в `generate_comic.py` или создадим `tts_utils.py` если кода будет много.

### 2.2 Модификация `generate_comic.py`
- Добавить функции `generate_tts`, `get_voice_config`, `calculate_voice_hash`.
- Расширить `main()` и цикл обработки сцен для вызова TTS.
- Добавить аргумент `--tts`.

---

## 3. Components

### 3.1 `voices.json` Structure
```json
{
  "narrator": {
    "provider": "elevenlabs",
    "voice_id": "pNInz6ovClqMvhaFY6HZ",
    "settings": {"stability": 0.5, "similarity_boost": 0.75}
  },
  "aleksey_38": {
    "provider": "yandex",
    "voice_id": "alena",
    "settings": {"speed": 1.0, "emotion": "neutral"}
  },
  "default": {
    "provider": "elevenlabs",
    "voice_id": "erXw6pcqS2QCpv69rqpG"
  }
}
```

### 3.2 TTS Implementation Details

#### ElevenLabs
- Использует библиотеку `elevenlabs` или прямой REST API.
- Требует `ELEVEN_API_KEY` в `.env`.

#### Yandex SpeechKit
- REST API.
- Требует `YANDEX_API_KEY` и `YANDEX_FOLDER_ID`.

#### Silero
- Локальная генерация через `torch` + `silero-models`.
- Полезно как fallback или для экономии бюджета.

### 3.3 Caching Strategy
- Файл: `output/audio/scene_XXX.mp3`.
- Метаданные кэша в `output/audio/cache.json`:
  ```json
  {
    "scene_001": {
      "hash": "sha256_of_text_plus_voice_settings",
      "provider": "elevenlabs"
    }
  }
  ```
- Если хэш совпадает и файл существует — пропускаем генерацию.

---

## 4. Pipeline Integration

```
Scene Loop
  ├─ ... (image generation)
  └─ If args.tts:
       ├─ Get voice config for scene.speaker
       ├─ Calculate hash(voice_text + config)
       ├─ Check cache
       ├─ If not in cache:
       │    └─ Call TTS Provider with retries
       └─ Save to output/audio/scene_XXX.mp3
```

---

## 5. Error Handling
- **429 Rate Limit**: Использовать существующую `backoff_delay` логику.
- **Missing Voice**: Использовать `default` из `voices.json` или `narrator` если `default` нет.
- **Provider Down**: Выбросить warning и пометить аудио как `failed`, но не останавливать весь пайплайн (картинки важнее).

---

## 6. Testing Plan
- Unit-тесты для `get_voice_config`.
- Mock-тесты для провайдеров (проверка формирования запросов).
- Проверка кэширования.

---

## 7. Dependencies
- `elevenlabs>=1.0.0`
- `requests` (для Yandex)
- `torch`, `torchaudio`, `omegaconf` (для Silero - опционально, лучше вынести в `requirements-tts.txt`)
