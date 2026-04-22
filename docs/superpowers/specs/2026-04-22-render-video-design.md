# `--render-video` — Design Spec

**Дата:** 2026-04-22
**Статус:** approved (brainstorming complete)
**Подпроект roadmap:** 3 (TODO.md раздел 3)
**Предшественник:** `--tts` (2026-04-21, готов)

---

## Цель

Одной командой собрать финальный mp4 из готовых артефактов пайплайна: `frame_*.png` + `audio/scene_*.mp3` + `subtitles.srt` + `design_spec.json` → `output/comic.mp4` с вшитыми (hard-sub) субтитрами.

Сейчас пользователь делает это вручную через ffmpeg. Эта фича закрывает последний ручной шаг пайплайна.

---

## Scope

**Входит в эту итерацию (MVP + burn-in subs):**

- Базовая склейка per-scene клипов → один mp4.
- Hard-sub через ASS-формат, стили из `design_spec.json`.
- Два пресета качества: `draft` (быстрый превью) / `final` (релиз).
- Два режима вызова: автостадия в конце пайплайна (`--render-video`) + standalone (`--render-video-only`).
- Hash-кэш per-scene mp4 для идемпотентного resume и итеративных правок.
- Fail-fast при отсутствующих ассетах + опциональный `--allow-incomplete`.

**НЕ входит (следующие итерации):**

- Ken Burns эффект (pan/zoom на статичных кадрах).
- Crossfade между сценами.
- Background music + auto-ducking.
- 9:16 / 1:1 / 4:5 aspect variants.
- Word-level timestamps синхронизация.

---

## Архитектура

### Файловая структура

```
output/
├── frame_*.png                  # существует
├── audio/scene_*.mp3            # существует (после --tts)
├── subtitles.srt                # существует
├── subtitles.ass                # НОВОЕ: генерится из SRT + design_spec
├── design_spec.json             # существует
├── progress.json                # расширяется: video_path, video_hash per scene
├── video/                       # НОВОЕ
│   ├── scene_001.mp4
│   ├── scene_002.mp4
│   └── ...
└── comic.mp4                    # НОВОЕ: финальный output (или --output)
```

### Поток рендера

```
1. Валидация: ffmpeg+ffprobe в PATH, все image/audio существуют,
              design_spec.json есть, progress.json не пустой
                          │
                          ▼
2. export_ass(design_spec, scenes, effective_durations) → subtitles.ass
                          │
                          ▼
3. for scene in scenes:
     hash = sha256(image_bytes + audio_bytes + scene_ass_block
                 + quality_preset + fps + resolution)
     if progress[scene].video_hash == hash and video_path exists:
         skip
     else:
         ffmpeg → scene_NNN.mp4.tmp → atomic rename → scene_NNN.mp4
         save_progress(video_path, video_hash)
                          │
                          ▼
4. Пишем concat_list.txt (ffconcat v1.0 + file scene_NNN.mp4)
                          │
                          ▼
5. ffmpeg -f concat -safe 0 -i list.txt -c copy comic.mp4
```

### Quality-пресеты

| quality | resolution | fps | crf | preset     | Использование                |
|---------|------------|-----|-----|------------|------------------------------|
| draft   | 1280×720   | 24  | 28  | ultrafast  | Итерации, превью, отладка    |
| final   | 1920×1080  | 30  | 18  | medium     | Релиз                        |

### Per-scene ffmpeg команда

```bash
ffmpeg -y \
  -loop 1 -i <image.png> \
  -i <audio.mp3> \
  -vf "scale=<W>:<H>,ass=subtitles.ass" \
  -t <effective_duration> \
  -c:v libx264 -crf <CRF> -preset <PRESET> \
  -pix_fmt yuv420p \
  -r <FPS> \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  <scene_NNN.mp4.tmp>
```

### Concat команда

```bash
ffmpeg -y -f concat -safe 0 -i concat_list.txt -c copy <output>.tmp
```

(затем atomic rename)

---

## Компоненты (функции)

Всё в `generate_comic.py` (монолит пока не трогаем, см. `CLAUDE.md`).

| Функция | Назначение |
|---|---|
| `check_ffmpeg() -> None` | Верификация ffmpeg+ffprobe в PATH. Fail-fast при отсутствии. |
| `probe_audio_duration(mp3_path) -> float` | Обёртка над `ffprobe -show_entries format=duration`. Для `effective_duration`. |
| `_hex_to_ass_color(hex_str) -> str` | `#RRGGBB` → `&H00BBGGRR` (ASS BGR + alpha). |
| `_fmt_ass_time(seconds) -> str` | `3.456` → `0:00:03.46` (centiseconds, не мс). |
| `scene_ass_block(idx, scenes, durations) -> str` | Одна строка `Dialogue:` для сцены. Используется в hash. |
| `export_ass(design_spec, scenes, durations) -> Path` | Полный `subtitles.ass` (Script Info + V4+ Styles + Events). |
| `compute_video_hash(img, audio, ass_block, quality, fps, res) -> str` | sha256 hex. |
| `render_scene_video(scene, ass_path, preset) -> Path` | Один ffmpeg на сцену. Идемпотентно (hash-чек). Атомарная запись. |
| `concat_scenes(mp4s, output_path) -> None` | Пишет list.txt, вызывает concat demuxer. |
| `render_video(scenes, design_spec, quality, output, allow_incomplete) -> Path` | Оркестратор. |

### Константы (добавить к существующим в начале файла)

```python
QUALITY_PRESETS = {
    "draft": {"res": (1280, 720),  "fps": 24, "crf": 28, "preset": "ultrafast"},
    "final": {"res": (1920, 1080), "fps": 30, "crf": 18, "preset": "medium"},
}
DEFAULT_VIDEO_OUTPUT = Path("output/comic.mp4")
SCENE_VIDEO_DIR = Path("output/video")
VIDEO_MAX_RETRIES = 3
```

### Расширение `progress.json` per-scene entry

```json
{
  "index": 1,
  "status": "ok",
  "image_path": "output/frame_001.png",
  "audio_path": "output/audio/scene_001.mp3",
  "video_path": "output/video/scene_001.mp4",
  "video_hash": "sha256:abc123..."
}
```

### CLI флаги

```
--render-video              # автостадия после TTS
--render-video-only         # standalone, пропускает split/prompts/images/tts
--quality {draft,final}     # default: draft
--output PATH               # default: output/comic.mp4
--allow-incomplete          # skip сцен без image/audio, иначе fail-fast
```

---

## ASS-генерация

### Маппинг `design_spec.json` → ASS `[V4+ Styles]`

Предполагаемые поля (уточняется при реализации после чтения реального `design_spec.json`):

| design_spec поле | ASS Style поле |
|---|---|
| `font_family` | `Fontname` |
| `font_size` | `Fontsize` (scale to target resolution) |
| `primary_color` (`#RRGGBB`) | `PrimaryColour` (`&H00BBGGRR`) |
| `outline_color` | `OutlineColour` |
| `outline_width` | `Outline` |
| `position` (`bottom-center` и т.д.) | `Alignment` (numpad: 2=bot-center, 5=mid-center, 8=top-center) |
| `margin_vertical` | `MarginV` |

### Dialogue события

Старты/концы накопительно из `effective_durations[i]`:

```
Dialogue: 0,0:00:00.00,0:00:03.45,Default,,0,0,0,,{voice_text сцены 1}
Dialogue: 0,0:00:03.45,0:00:07.12,Default,,0,0,0,,{voice_text сцены 2}
```

### `effective_duration` для видео

Та же логика что в SRT (см. существующую функцию `effective_duration`):

1. Если `audio_path` есть и файл валиден → `probe_audio_duration(mp3)`.
2. Иначе → `scene.duration_sec` из progress.
3. Иначе → `estimate_duration(voice_text)`.

При `--allow-incomplete` сцена без mp3 → тишина длины п.2/п.3.

### Edge case: шрифт не установлен

libass молча откатывается на fallback (обычно Arial, выглядит не так). Решение:

- Опциональный env-var `COMIC_FONTS_DIR` → ffmpeg flag `-vf "ass=subs.ass:fontsdir=${COMIC_FONTS_DIR}"`.
- При `export_ass`: если env-var не задан и `font_family` не Arial/DejaVu (базовые) — `log.warning("Font '%s' may not render correctly. Set COMIC_FONTS_DIR.")`.
- Не fail-fast — warning достаточно.

---

## Обработка ошибок

### Fail-fast предусловия (`render_video` вход)

| Проверка | Действие |
|---|---|
| `ffmpeg` / `ffprobe` нет в PATH | `RuntimeError("ffmpeg not found. Install: https://ffmpeg.org")` |
| `progress.json` отсутствует / пустой | `RuntimeError("No scenes to render. Run pipeline first.")` |
| `design_spec.json` отсутствует | `RuntimeError("design_spec.json missing. Run --bootstrap.")` |
| Сцена без `image_path` или файл отсутствует | Fail-fast без `--allow-incomplete`; иначе skip + warning |
| Сцена без `audio_path` или файл отсутствует | То же |
| `output/video/` не существует | `mkdir(parents=True, exist_ok=True)` |

### Per-scene ffmpeg ошибки

- Retry до `VIDEO_MAX_RETRIES=3` с exponential backoff (2с, 8с между попытками).
- После исчерпания: `status=video_error` в `progress.json`, продолжаем остальные сцены.
- В конце — если есть `video_error` сцены: warning с перечнем.
- Concat НЕ запускается если есть ошибки И не задан `--allow-incomplete`.

### Concat-стадия ошибки

- Если `scene_NNN.mp4` отсутствует для сцены со `status=ok` — fail-fast.
- Если `--allow-incomplete` и есть пропуски — concat из имеющихся, warning `"пропущено N сцен: [idx1, idx2, ...]"`.

### Идемпотентность

- Hash-чек перед каждым per-scene ffmpeg. Совпало → skip.
- Concat дешёвый (без перекодирования) — всегда перезапускается.
- Повторный запуск `--render-video-only` без изменений → 0 per-scene ffmpeg, только concat.

### Атомарность

- Per-scene: ffmpeg пишет в `scene_NNN.mp4.tmp` → `os.replace()` → `scene_NNN.mp4`.
- Final output: `comic.mp4.tmp` → `os.replace()` → `comic.mp4`.
- Прерывание (Ctrl+C) → `.tmp` файлы остаются, игнорируются при resume (hash не матчит).

### Logging

- `log.info` — вход/выход `render_video`, старт/конец per-scene рендера (`🎬 scene 23/128 rendered in 4.1s`), concat-стадия.
- `log.warning` — skip сцены, retry ffmpeg, incomplete concat.
- `log.error` — fatal (ffmpeg not found, progress.json missing).

---

## Тестирование

Следуем политике проекта (`CLAUDE.md`): unit-тесты для чистых функций. Integration — отдельно.

### Unit-тесты (`tests/test_pure.py` или новый `tests/test_video.py`)

| Тест | Что проверяет |
|---|---|
| `test_compute_video_hash_stable` | Одинаковые inputs → одинаковый hash. |
| `test_compute_video_hash_sensitivity` | Изменение image/audio/ass/quality/fps/res → hash меняется. |
| `test_scene_ass_block_deterministic` | Одна `Dialogue:` строка, формат валидный. |
| `test_fmt_ass_time` | `0.0 → "0:00:00.00"`, `3.456 → "0:00:03.46"`, `3661.5 → "1:01:01.50"`. |
| `test_hex_to_ass_color` | `"#FF0000" → "&H000000FF"`, `"#00FF00" → "&H0000FF00"`, `"#000000" → "&H00000000"`. |
| `test_export_ass_structure` | На тестовом design_spec + 3 сценах — валидный ASS header + styles + events в правильном порядке. |
| `test_quality_preset_mapping` | `QUALITY_PRESETS["draft"]` и `final` содержат `res`, `fps`, `crf`, `preset`. |

### Integration smoke test (`tests/test_video_integration.py`, `@pytest.mark.integration`)

Использует реальные ассеты из `output/`. Skip по-дефолту, запускается `pytest -m integration`.

- Вход: `output/frame_001.png`, `output/audio/scene_001.mp3`, `output/design_spec.json`, минимальный `progress.json` с одной сценой.
- Вызов: `render_scene_video(scene_1, ass_path, quality="draft")`.
- Output: `tests/tmp/scene_001.mp4` (cleanup в teardown).
- Ассерты:
  - Файл создан, размер > 0.
  - `ffprobe` duration ≈ real mp3 duration (±0.1с).
  - Кодек `h264`, разрешение 1280×720.
  - Hash совпадает с `compute_video_hash(...)`.

### Ручной smoke test (чеклист в плане реализации)

1. `python generate_comic.py --render-video-only --limit 3 --quality draft --allow-incomplete` → `output/comic.mp4` с 3 клипами.
2. Повторный запуск → 0 per-scene ffmpeg, только concat.
3. Правка `design_spec.json` (цвет шрифта) → повторный запуск → все 3 сцены пересобраны, субтитры нового цвета.
4. `--quality final` после `draft` → все 3 пересобраны в 1080p.
5. Открыть `comic.mp4` в плеере — субтитры видны, аудио синхронно, стили применены.

### НЕ покрываем в этой итерации

- Реальные ffmpeg-вызовы полной склейки 100+ сцен.
- Визуальная валидация output (diff с эталонным видео).
- Concat с моком ffmpeg — integration, отдельный подпроект.

---

## Зависимости

### Системные

- **ffmpeg ≥ 4.x** с поддержкой libx264, libass, aac encoder. Проверяется `check_ffmpeg()`.
- **ffprobe** (поставляется с ffmpeg).

### Python

- Ничего нового. `subprocess` стандартной библиотеки. `hashlib` для sha256.
- Шрифты — опционально через env-var `COMIC_FONTS_DIR`.

---

## Изменения в существующих файлах

| Файл | Изменения |
|---|---|
| `generate_comic.py` | +9 новых функций (список выше), расширение `main()` для `--render-video`/`--render-video-only`/`--quality`/`--output`/`--allow-incomplete`, добавление `video_path`/`video_hash` в сохранение progress. |
| `schemas.py` | Опционально: pydantic-схема для `DesignSpec` с полями font/color/etc. Если решим валидировать `design_spec.json`. (Ниже в Open Questions.) |
| `README.md` | Секция `--render-video` с примерами использования. |
| `TODO.md` | Вычеркнуть раздел 3 (базовая склейка + burn-in). Оставить Ken Burns/crossfade/BGM/9:16 для следующих итераций. |
| `CLAUDE.md` | Обновить «Архитектура» (добавить render_video стадию), «Статус: что сделано» (добавить `--render-video`), «Roadmap» (сдвинуть пункты). |
| `tests/test_pure.py` или `tests/test_video.py` | Новые unit-тесты. |
| `tests/test_video_integration.py` | Integration smoke test с `@pytest.mark.integration`. |
| `pyproject.toml` / `setup.cfg` | Регистрация `integration` marker в pytest. |

---

## Open Questions (решаются при реализации)

1. **Реальная схема `design_spec.json`** — нужно прочитать существующий файл в `output/` и сверить ожидаемые поля. Возможно добавить pydantic-схему `DesignSpec` в `schemas.py` с ретраем при невалидном формате (следуя паттерну остальных LLM-ответов).
2. **Нужен ли `scale` filter перед `ass`?** — если входные PNG уже 16:9 в правильном разрешении, `scale` избыточен. Проверить размеры `output/frame_001.png` при реализации.
3. **Font fallback** — если решим что warning недостаточно, добавить pre-check через `fc-list` (не работает на Windows из коробки). Пока warning + env-var.

---

## Связь с roadmap

После этой итерации TODO раздел 3 закрывается на 🔴-уровень. Следующие фичи того же раздела (Ken Burns, crossfade, BGM, 9:16) — отдельные подпроекты.

Roadmap после завершения:

1. ✅ TTS-интеграция
2. ✅ `--render-video` (эта итерация)
3. `--scene N` + параллельная генерация (TODO раздел 1)
4. Usage tracking + `--estimate` (TODO раздел 6)
5. Рефакторинг монолита (TODO раздел 9)
