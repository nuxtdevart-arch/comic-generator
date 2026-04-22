# Comic Frame Generator — Soviet Comic-Noir

Python-скрипт, который превращает прозаический текст (`story.txt`) в **готовый к видеомонтажу пакет**: кадры комикса, референсы персонажей, субтитры и дизайн-спецификацию — через Gemini API + nano-banana. Полная автоматизация от одного файла `story.txt`.

---

## Что получишь на выходе

```
output/
├── frame_001.png … frame_NNN.png     # кадры комикса (16:9, safe zone снизу)
├── prompts.json                       # все сцены + voice_text + subtitle_lines + duration
├── progress.json                      # состояние для --resume (включая batch_job_name)
├── design_spec.json                   # font/color/position для субтитров
└── subtitles.srt                      # готовый SRT с таймингами

references/
├── aleksey_38.png                     # авто-сгенерированные портреты
└── …                                  # (по одному на каждого персонажа)

characters.json                         # авто-заполняется из story.txt
```

TTS уже встроен — см. секцию TTS-озвучка ниже. Видеосборка пока через ffmpeg вручную (скоро будет `--render-video`).

---

## Установка

```bash
pip install google-genai python-dotenv
echo "GEMINI_API_KEY=твой_ключ" > .env
```

Ключ: https://aistudio.google.com/apikey. Требуется **Tier 1** (Paid billing). Проверить: https://aistudio.google.com/rate-limit.

---

## Полная автоматизация с нуля

```bash
python generate_comic.py --story story.txt --bootstrap --batch
```

Пайплайн:

1. **Bootstrap** — один LLM-скан всего story → `characters.json` заполнен.
2. **Reference synthesis** — nano-banana рисует portrait для каждого персонажа → `references/*.png`.
3. **Design spec** — LLM предлагает font/color/layout для субтитров → `design_spec.json`.
4. **Split story** — детерминированное разбиение на сцены → `progress.json`.
5. **Batch scene prompts** — все сцены в один Gemini Batch job (50% дешевле): prompt + voice_text + emotion + subtitle_lines.
6. **Image gen** — nano-banana по каждому кадру с привязкой reference-картинок.
7. **SRT export** — `subtitles.srt` с таймингами.

**Оценка стоимости для 128 сцен с нуля**: ~$6–8.

---

## Использование (отдельные режимы)

### Dry-run — только промпты и метадата, без картинок

```bash
python generate_comic.py --story story.txt --bootstrap --batch --dry-run
```

Дешёвый smoke test (~$0.50). В dry-run **не** генерятся portrait-референсы и кадры.

### Если `characters.json` и `references/` уже готовы вручную

```bash
python generate_comic.py --story story.txt --batch
```

Без `--bootstrap` — скрипт не трогает `characters.json` и не рисует портреты.

### Resume после прерывания

```bash
python generate_comic.py --story story.txt --batch --resume
```

- Возобновляет с первой сцены, у которой `status != ok|skipped`.
- Если batch job висел — подхватывает его из `progress.json` (`batch_job_name`), не создаёт новый.

### Перезаписать characters.json с нуля

```bash
python generate_comic.py --story story.txt --bootstrap --bootstrap-force
```

Полезно если story сильно переписан и надо пересобрать dossier.

### Тест на первых N сценах

```bash
python generate_comic.py --story story.txt --bootstrap --batch --limit 3
```

### Принудительно Gemini 2.5 Pro для всех LLM-операций

```bash
python generate_comic.py --story story.txt --force-pro
```

### Verbose-лог

```bash
python generate_comic.py --story story.txt --verbose
```

---

## Структура файлов

```
./
├── generate_comic.py
├── story.txt                  # твой текст (целиком, русский)
├── characters.json            # авто-заполняется через --bootstrap
├── .env                       # GEMINI_API_KEY
├── references/                # PNG-референсы (авто-генерятся)
└── output/                    # кадры + метаданные + SRT
```

---

## Модели и авто-выбор

| Задача | Основная модель | Fallback / эскалация |
|---|---|---|
| Bootstrap characters | `gemini-2.5-flash` | `gemini-2.5-flash-lite` |
| Split story на сцены | `gemini-2.5-flash` | `gemini-2.5-flash-lite` (fallback), `gemini-2.5-pro` (`--force-pro`) |
| Scene prompts (prompt + voice + subs) | `gemini-2.5-flash` | `gemini-2.5-flash-lite` (fallback), `gemini-2.5-pro` (при ≥4 персонажей ИЛИ тексте ≥900 символов ИЛИ падении Flash) |
| Design spec | `gemini-2.5-flash` | `gemini-2.5-flash-lite` |
| Reference portrait | `gemini-2.5-flash-image` (nano-banana) | — |
| Scene frame | `gemini-2.5-flash-image` (nano-banana) | — |

**Split и bootstrap детерминированы**: `temperature=0` + `thinking_budget=0`.

---

## Формат сцены (`prompts.json` / `progress.json`)

```json
{
  "index": 1,
  "text": "3 часа ночи. Ты сидишь в туалете...",
  "title": "Bathroom 3am",
  "character_ids": ["aleksey_38"],
  "prompt": "cinematic English paragraph + style suffix",
  "status": "ok",
  "error": "",
  "image_path": "output/frame_001.png",
  "model_used": "gemini-2.5-flash",
  "voice_text": "3 часа ночи. Я сижу в туалете...",
  "speaker": "narrator",
  "emotion": "melancholic introspective",
  "pacing": "slow",
  "duration_sec": 6.4,
  "subtitle_lines": ["3 часа ночи.", "Я сижу в туалете."]
}
```

`status` ∈ `pending | ok | skipped | error`.
SRT экспортируется только из сцен со `status == ok`.

---

## Субтитры и озвучка

### `subtitles.srt`

Стандартный SRT — открывается в Premiere, DaVinci, ffmpeg, VLC. Тайминги построены последовательно: каждый cue начинается сразу после предыдущего. Длительность сцены = `duration_sec` (оценка из `voice_text` и `pacing`).

### `design_spec.json` (подсказка для видеоредактора)

```json
{
  "font_family": "PT Sans Narrow",
  "font_weight": 600,
  "font_size_px": 42,
  "color_fg": "#E8C77D",
  "color_bg_gradient": ["#000000CC", "#00000000"],
  "stroke_px": 2,
  "stroke_color": "#000000",
  "position": "bottom_centered",
  "margin_bottom_pct": 8,
  "narrator_style": "italic",
  "dialogue_style": "regular",
  "rationale": "..."
}
```

### ffmpeg-склейка (пример)

Временно: пока нет `--render-video`, склейка руками:
```bash
ffmpeg -framerate 1/5 -i output/frame_%03d.png \
       -i voice.mp3 \
       -vf "subtitles=output/subtitles.srt" \
       -c:v libx264 -pix_fmt yuv420p out.mp4
```

---

## Устойчивость к сбоям

Против 503 UNAVAILABLE (перегрузка Gemini) и 429 (rate limit):

- **classify_error()** — различает `429/503/5xx/fatal/timeout`, парсит `Retry-After`.
- **Full-jitter exponential backoff**: overload/rate_limit cap = 300с, прочие 5xx cap = 120с.
- **Retry-After** из ответа уважается.
- **Fast fallback**: после 3 подряд 503 → моментальный переход на `gemini-2.5-flash-lite`.
- **Fatal (400/401/403/404)** — без ретраев.
- **Отдельный retry-бюджет для картинок**: `IMAGE_MAX_RETRIES=10`.
- **Per-scene `save_progress`** после каждой сцены.
- **Split сохраняется мгновенно** → сцены не теряются при падении.
- **`batch_job_name` персистится** → `--resume` подхватывает незавершённый batch.

---

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

---

## Тесты

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Покрыто: 5 чистых функций (`classify_error`, `backoff_delay`, `_fmt_srt_time`, `estimate_duration`, `pick_scene_model`) и pydantic-схемы для 4 LLM-ответов. Validation-fail вызывает re-prompt LLM с текстом ошибки.

---

## Новый персонаж, появившийся уже в середине работы

Если в сцене обнаружен персонаж, которого не было в `characters.json`:

1. Запись добавляется в `characters.json` с `"_auto_generated": true`.
2. Сцена помечается `skipped` — нет reference-картинки.
3. Для получения картинки: запусти `--bootstrap` — сгенерит portrait, потом `--resume` добьёт сцены.

---

## Возрастные варианты Алексея/Лёши

`lyosha_5`, `lyosha_8`, `lyosha_12`, `lyosha_15`, `aleksey_17`, `aleksey_18`, `aleksey_19`, `aleksey_38` — LLM сам выбирает нужный id по году/контексту сцены. Если промахивается:

- Уточни год в тексте сцены: `(1994)`, `(2003)`.
- Добавь год рождения в description — модель увидит в dossier.

---

## Troubleshooting

| Проблема | Фикс |
|---|---|
| `ERROR: set GEMINI_API_KEY` | `export GEMINI_API_KEY=...` или `.env` |
| `Missing reference: references/xxx.png` | Запусти `--bootstrap` для генерации портрета |
| 503 UNAVAILABLE спам | Скрипт сам ретраит + fallback. Если шторм глобальный — подожди 10–15 мин или `--batch` |
| Застрял на Free tier при оплаченном биллинге | Ключ из не-billing проекта. Перегенери: https://aistudio.google.com/apikey |
| Batch PENDING надолго | Нормально до 5 мин. `--resume --batch` подхватит job |
| Character consistency плохая | Чёткие референсы. При 4+ персонажах — качество падает |
| Субтитры разбиты криво | LLM выдаёт `subtitle_lines` по-своему. Можешь постобработать `prompts.json` скриптом. Предел: 42 симв/линия, 2 линии |

---

## Полезные ссылки

- Rate limits dashboard: https://aistudio.google.com/rate-limit
- API keys: https://aistudio.google.com/apikey
- Billing: https://ai.google.dev/gemini-api/docs/billing
- Batch API: https://ai.google.dev/gemini-api/docs/batch-mode
- Rate limits doc: https://ai.google.dev/gemini-api/docs/rate-limits
- Google Cloud status: https://status.cloud.google.com/
- Pricing: https://ai.google.dev/gemini-api/docs/pricing

---

## Оценка стоимости (128 сцен, Tier 1)

| Этап | Стоимость |
|---|---|
| Bootstrap scan | ~$0.02 |
| Reference portraits (×33) | ~$1.30 |
| Design spec | ~$0.01 |
| Split story | ~$0.01 |
| Batch scene prompts | ~$0.30 |
| Image gen (×128) | ~$5.00 |
| **Итого** | **~$6.64** |

Dry-run (без картинок и портретов): **~$0.35**.

---

## TODO

- `--scene N` — перегенерировать конкретный кадр.
- Параллельная генерация картинок.
- Context caching для dossier + story (-75% на повторяющейся части).
- `--render-video` — ffmpeg-склейка кадров + голоса + SRT.
- Авто-подбор голоса per-speaker через TTS-бэкенд.
