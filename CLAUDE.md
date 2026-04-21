# CLAUDE.md — Comic Frame Generator

Этот файл — первичная точка входа для Claude Code в этом проекте. Читается автоматически при старте сессии.

---

## Что это

Персональный CLI-скрипт, который превращает прозаический текст (`story.txt`, русский) в **готовый к видеомонтажу пакет**: кадры комикса (16:9, стиль «Soviet comic-noir»), референсы персонажей, субтитры (SRT), дизайн-спецификацию.

Запуск end-to-end:
```bash
python generate_comic.py --story story.txt --bootstrap --batch
```

Модели: Google Gemini API + nano-banana (`gemini-2.5-flash-image`). Python 3.14.

**Не веб-сервис. Не production-библиотека.** Это инструмент одного автора для создания конкретного комикса из автобиографической прозы.

---

## Архитектура

```
┌───────────────┐
│  story.txt    │  русская проза, 40-50k символов
└──────┬────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│  generate_comic.py (~1050 строк, всё в одном файле пока что) │
└──────┬───────────────────────────────────────────────────────┘
       │
       ├─ bootstrap ────────► characters.json   (Gemini Flash, 1 вызов)
       ├─ reference synth ──► references/*.png  (nano-banana, N портретов)
       ├─ design spec ──────► design_spec.json  (Gemini Flash)
       ├─ split story ──────► progress.json     (Gemini Flash, детерминированный)
       ├─ batch scene gen ──► prompts.json      (Gemini Batch, 50% дешевле)
       ├─ image gen ────────► output/frame_*.png (nano-banana, N кадров)
       └─ SRT export ───────► output/subtitles.srt
```

### Главные функции (строки в `generate_comic.py`)

| Функция | Строка | Назначение |
|---|---|---|
| `classify_error` | 149 | Классификатор API-ошибок (`rate_limit`/`overload`/`server`/`timeout`/`fatal`/`unknown`) |
| `backoff_delay` | 172 | Full-jitter exponential backoff, уважает Retry-After |
| `call_llm_json` | 185 | Универсальная обёртка над Gemini text API с retry + fallback |
| `pick_scene_model` | 261 | Выбор модели (Flash vs Pro) по сложности сцены |
| `split_story` | 299 | Разбивка прозы на кинематографические сцены |
| `build_scene_prompt` | 385 | Построение prompt + метаданных для одной сцены |
| `batch_create_scene_prompts` | 461 | Отправка всех сцен одним batch-запросом |
| `batch_collect_scene_prompts` | 483 | Polling + parsing batch-ответов |
| `generate_image` | 527 | Nano-banana: кадр по prompt + референсам |
| `bootstrap_characters` | 608 | Скан story → characters.json |
| `generate_character_references` | 645 | Рендер портретов для references/ |
| `generate_design_spec` | 717 | Spec для субтитров (font/color/position) |
| `estimate_duration` | 738 | Длительность сцены из voice_text + pacing |
| `_fmt_srt_time` | 748 | Форматирование `HH:MM:SS,mmm` |
| `export_srt` | 756 | Запись `subtitles.srt` |
| `main` | 784 | CLI argparse + orchestration |

### Основные константы (строки 57-98)

- `STYLE_SUFFIX`, `PORTRAIT_STYLE_SUFFIX` — стилевой хвост промптов.
- `FLASH_MODEL = "gemini-2.5-flash"`, `PRO_MODEL = "gemini-2.5-pro"`, `IMAGE_MODEL = "gemini-2.5-flash-image"`.
- `MAX_RETRIES = 8`, `IMAGE_MAX_RETRIES = 10`.
- `BACKOFF_CAP = 120.0`, `BACKOFF_CAP_503 = 300.0`.
- `COMPLEX_SCENE_CHAR_THRESHOLD = 4`, `COMPLEX_SCENE_LENGTH_CHARS = 900` — пороги эскалации Flash→Pro.
- `SUBTITLE_MAX_CHARS_PER_LINE = 42`, `RU_WORDS_PER_SEC = 2.5`.

### Устойчивость к сбоям

- `classify_error` различает `429` / `503` / `5xx` / `fatal` / `timeout` по тексту исключения.
- Full-jitter exponential backoff; cap 300с для overload/rate-limit, 120с для прочих.
- Fast fallback: 3 подряд 503 → моментальный переход на `gemini-2.5-flash-lite`.
- Per-scene `save_progress` — `--resume` подхватывает после любого падения.
- `batch_job_name` персистится в `progress.json` — незавершённый batch не создаётся заново.

---

## Файлы и что они делают

```
./
├── generate_comic.py        # весь скрипт, пока монолит
├── story.txt                # входной текст (русская проза)
├── characters.json          # dossier: id → {name, description, reference_image}
├── .env                     # GEMINI_API_KEY
├── README.md                # пользовательская документация
├── TODO.md                  # roadmap с приоритетами 🔴🟡🟢
├── CLAUDE.md                # ← этот файл
├── references/              # PNG-портреты персонажей (генерируются)
├── output/
│   ├── frame_*.png          # кадры комикса
│   ├── prompts.json         # финальные prompt + метадата для всех сцен
│   ├── progress.json        # состояние пайплайна для --resume
│   ├── design_spec.json     # font/color/position для субтитров
│   └── subtitles.srt        # SRT с таймингами
└── docs/superpowers/
    ├── specs/               # design-specs per подпроект
    └── plans/               # реализационные планы per подпроект
```

---

## Статус: что сделано, что в работе

### ✅ Готово

- End-to-end пайплайн: story.txt → кадры + SRT одной командой.
- Bootstrap characters автоматически.
- Batch-режим (50% дешевле на scene prompts).
- `--resume` после прерывания, включая полуготовый batch.
- Retry + fallback на уровне модели (Flash→Lite, Pro→Flash).
- SRT-экспорт с таймингами из `duration_sec` + `pacing`.

### 🚧 В работе (апрель 2026)

**Подпроект 1: Unit-тесты + schema validation** (TODO раздел 8, пункты 🔴)

- Спецификация: `docs/superpowers/specs/2026-04-21-tests-schema-validation-design.md`
- План: `docs/superpowers/plans/2026-04-21-tests-schema-validation.md`
- Статус: спец и план утверждены, реализация не начата.
- Scope:
  - ✅ Pure-функции покрыты тестами (task 11 плана).
  - pytest-покрытие 5 чистых функций (`classify_error`, `backoff_delay`, `_fmt_srt_time`, `estimate_duration`, `pick_scene_model`).
  - pydantic-валидация 4 LLM-ответов (`split`, `bootstrap`, `scene prompts`, `design spec`).
  - Retry-on-validation-fail: при `ValidationError` → re-prompt с текстом ошибки.
  - Новые файлы: `schemas.py`, `tests/`, `requirements-dev.txt`, `.gitignore`.
  - Git init (проект пока не под VCS).

**Не входит в текущую итерацию**:
- Integration-тесты с mock `genai.Client`
- Golden-тест SRT
- Chaos-тесты
- Coverage, CI

---

## Roadmap (из TODO.md)

Порядок реализации, утверждённый автором:

1. **Тесты + schema validation** ← в работе
2. **TTS-интеграция** (TODO раздел 2): `--tts elevenlabs|yandex|silero`, `voices.json`, `output/audio/scene_*.mp3`
3. **`--render-video`** (TODO раздел 3): финальная ffmpeg-склейка кадров + голоса + SRT → mp4
4. **`--scene N` + параллельная генерация** (TODO раздел 1)
5. **Usage tracking + `--estimate`** (TODO раздел 6)
6. **Рефакторинг монолита** (TODO раздел 9): разбивка на `comic/*.py` модули

Каждый пункт идёт через цикл: brainstorming → спец в `docs/superpowers/specs/` → план в `docs/superpowers/plans/` → реализация.

Полный список фич с приоритетами 🔴🟡🟢 — в `TODO.md`.

---

## Правила и конвенции

### Общие

- **Сейчас монолит.** `generate_comic.py` ~1050 строк. Разбиение на модули — отдельный подпроект (пункт 6 roadmap), пока не трогаем.
- **YAGNI.** Фичи добавляются только когда автор попросил. Не предлагать абстракции «на будущее».
- **Персональный инструмент.** Нет обратной совместимости, нет публичного API, нет стабильных контрактов. Можно ломать.

### Код

- Python 3.14, без type-annotations-магии. Простой процедурный стиль.
- Все константы — SCREAMING_SNAKE_CASE в начале файла.
- `dataclass` для `Scene`, иначе — dict'ы.
- Логирование через `log = logging.getLogger("comic")`. Уровни: `info` для этапов пайплайна, `warning` для retry/fallback, `error` для fatal.
- Имена файлов и пути строить через `pathlib.Path`.
- JSON — `json.dumps(..., ensure_ascii=False, indent=2)`. Никогда не экранировать кириллицу.

### LLM-интеграция

- JSON-ответы читать только через `call_llm_json`. Не дублировать retry-логику.
- После подпроекта 1: всегда передавать `schema=...` в `call_llm_json` для новых LLM-вызовов.
- Детерминированные вызовы (bootstrap, split, design spec) — `deterministic=True`.
- Эскалация Flash→Pro только на явных триггерах (`pick_scene_model`), не на каждой ошибке.
- Batch-режим — для дешёвых массовых операций (scene prompts), НЕ для реалтайм-задач и НЕ для картинок.

### Тесты (после подпроекта 1)

- `pytest tests/ -v` — все тесты должны быть зелёные перед коммитом.
- Характеризационные тесты для существующих чистых функций (фиксируем поведение as-is).
- TDD для новых схем: тест → fail → реализация → pass → commit.
- Изолированные unit-тесты, без реальных API-вызовов. Integration-тесты с моком — отдельный подпроект.

### Git

- Проект переходит под Git в рамках подпроекта 1 (задача 0 плана).
- Атомарные коммиты: каждый проходит `pytest`.
- Commit-style: `<type>(<scope>): <what>` (conventional), пример: `feat(schemas): ScenePromptResponse with validators`.
- Не коммитить: `.env`, `output/*.png`, `references/*.png`, `__pycache__/`, `*.pyc`, `.pytest_cache/`.

### Документация

- Новые фичи → обновлять `README.md` (пользовательская часть) и `TODO.md` (вычёркивать сделанное).
- Архитектурные изменения → обновлять этот `CLAUDE.md` (особенно секции «Архитектура» и «Статус»).
- Специфики реализации → `docs/superpowers/specs/` и `docs/superpowers/plans/` с датой в имени.

### Безопасность и приватность

- `story.txt` автобиографический, содержит персональные данные. **Никогда** не коммитить в публичный репозиторий без предварительного разрешения автора.
- `.env` содержит `GEMINI_API_KEY` — в `.gitignore`, в логах не светить (Gemini иногда включает ключ в текст ошибок — при показе логов автору проверять).
- Gemini API логирует запросы. Для чувствительного контента — рассматривать Vertex AI с privacy mode (пока не реализовано).

---

## Частые команды

```bash
# Полный пайплайн с нуля
python generate_comic.py --story story.txt --bootstrap --batch

# Dry-run (без картинок, ~$0.50)
python generate_comic.py --story story.txt --bootstrap --batch --dry-run

# Resume после прерывания
python generate_comic.py --story story.txt --batch --resume

# Тест на N сценах
python generate_comic.py --story story.txt --bootstrap --batch --limit 3

# Verbose
python generate_comic.py --story story.txt --verbose

# Тесты (после реализации подпроекта 1)
pytest tests/ -v

# Установка dev-deps (после реализации подпроекта 1)
pip install -r requirements-dev.txt
```

---

## Как вести сессию

**Когда автор просит новую фичу:**

1. Проверить, есть ли она в `TODO.md`. Если да — использовать формулировку оттуда.
2. Если задача не тривиальная (3+ шагов) — идти через brainstorming-скилл, писать спец в `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`, затем план в `docs/superpowers/plans/`.
3. Не реализовывать фичу без утверждённого плана.

**Когда автор просит правку существующего:**

1. Сначала прочитать соответствующую функцию в `generate_comic.py`.
2. Минимальное изменение, которое решает задачу. Не рефакторить попутно.
3. Если затрагивается LLM-интеграция — идти через `call_llm_json`, не дублировать retry-логику.

**При ошибках пайплайна у автора:**

1. Спросить полный лог с `--verbose`.
2. Проверить `output/progress.json` — где застряло.
3. Классифицировать: 429/503 → ждать + `--resume`; schema fail → re-prompt сработал или нет; fatal → правка кода/конфига.

**Caveman mode:** активен для этого пользователя по-умолчанию (через SessionStart hook). Коммуникация — фрагменты, без артиклей/филлера. Код/коммиты/документация — нормальным стилем.

---

## Контакты

Автор: `frontdevart@gmail.com`
