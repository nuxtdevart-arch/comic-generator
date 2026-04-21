# Unit Tests + LLM Schema Validation — Design

**Date:** 2026-04-21
**Scope:** TODO.md раздел 8 — минимальный срез (пункты 🔴 + фундамент).
**Status:** Draft, pending user approval.

---

## 1. Goal

Закрыть два красных пункта из раздела 8 TODO:

1. **Unit-тесты** для чистых функций: `classify_error`, `backoff_delay`, `_fmt_srt_time`, `estimate_duration`, `pick_scene_model`.
2. **Schema validation** ответов LLM через pydantic для всех четырёх JSON-вызовов (split, bootstrap, scene prompts, design spec).

**Не входит в scope этой итерации** (вынесены в следующие specы):

- Integration-тесты с моknutым `genai.Client`.
- Golden-тест для SRT.
- Retry-бюджет с предохранителем.
- Chaos-тесты.
- Coverage reporting.
- CI / GitHub Actions.

---

## 2. Architecture

Два новых файла плюс патчи к `generate_comic.py`.

```
schemas.py                      # pydantic-модели для 4 LLM-ответов
tests/
  __init__.py
  conftest.py                   # sys.path shim для импорта из root
  test_pure.py                  # 5 чистых функций
  test_schemas.py               # happy + invalid кейсы на модель
requirements-dev.txt            # pytest>=8.0
```

### Принципы

- Модели изолированы в `schemas.py` — лёгко импортируются в тесты без запуска main-пайплайна.
- `call_llm_json` получает необязательный параметр `schema: type[BaseModel] | None = None` — существующие call-sites работают без изменений до подключения.
- Валидация встроена в retry-loop: при `ValidationError` делается re-prompt с приложенным текстом ошибки, до исчерпания `MAX_RETRIES`.
- Возвращаем `.model_dump()` — call-sites, читающие `data.get(...)`, продолжают работать без правок.
- `extra="allow"` на всех моделях — LLM может добавлять поля, не ломаем пайплайн.

---

## 3. Components

### 3.1 `schemas.py`

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


# ── 1. split_story ────────────────────────────────────────────────
class SplitScene(_Base):
    text: str = Field(min_length=1)
    title: str = ""


class SplitResponse(_Base):
    scenes: list[SplitScene] = Field(min_length=1)


# ── 2. bootstrap_characters ───────────────────────────────────────
class BootstrapCharacter(_Base):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class CharactersResponse(_Base):
    characters: list[BootstrapCharacter]


# ── 3. build_scene_prompt (realtime и batch) ──────────────────────
class NewCharacter(_Base):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class ScenePromptResponse(_Base):
    existing_character_ids: list[str] = []
    new_characters: list[NewCharacter] = []
    prompt: str = Field(min_length=1)
    voice_text: str = Field(min_length=1)
    speaker: str = "narrator"
    emotion: str = ""
    pacing: str = "normal"
    subtitle_lines: list[str] = Field(min_length=1, max_length=3)

    @field_validator("pacing")
    @classmethod
    def _pacing_enum(cls, v: str) -> str:
        if v not in {"slow", "normal", "fast"}:
            raise ValueError(f"pacing must be slow|normal|fast, got {v!r}")
        return v

    @field_validator("subtitle_lines")
    @classmethod
    def _line_length(cls, v: list[str]) -> list[str]:
        for line in v:
            if len(line) > 42:
                raise ValueError(f"subtitle line exceeds 42 chars: {line!r}")
        return v


# ── 4. design_spec ────────────────────────────────────────────────
class DesignSpec(_Base):
    font_family: str = Field(min_length=1)
    font_weight: int = Field(ge=100, le=900)
    font_size_px: int = Field(ge=12, le=200)
    color_fg: str = Field(pattern=r"^#[0-9A-Fa-f]{6,8}$")
    color_bg_gradient: list[str] = Field(min_length=2, max_length=2)
    stroke_px: int = Field(ge=0)
    stroke_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6,8}$")
    position: str = Field(min_length=1)
    margin_bottom_pct: int = Field(ge=0, le=50)
    narrator_style: str = "italic"
    dialogue_style: str = "regular"
    rationale: str = ""
```

### 3.2 `call_llm_json` — изменения

**Новая сигнатура:**

```python
def call_llm_json(
    client: genai.Client,
    model: str,
    prompt: str,
    system: str | None = None,
    deterministic: bool = False,
    schema: type[BaseModel] | None = None,
) -> Any:
```

**Ключевое изменение в retry-loop:**

- Базовый prompt сохраняется в локальной переменной `base_prompt = prompt` до входа в цикл. Каждый retry на validation-fail делает `prompt = base_prompt + error_suffix`, ошибки не накапливаются.
- После `json.loads(text)`: если `schema is not None`, вызываем `schema.model_validate(data)`. На успех — `return .model_dump()`. На `ValidationError` — логируем, строим error-suffix, устанавливаем `kind="validation"`, `consec_overload = 0`, переходим к `backoff_delay`.
- Validation-fail считается в общий бюджет `MAX_RETRIES`, не отдельный.
- Fallback-модель получает тот же `schema`.

**Error-suffix формат:**

```
\n\nPREVIOUS RESPONSE FAILED SCHEMA VALIDATION:
{str(validation_error)}

Return valid JSON matching the schema exactly.
```

### 3.3 Call-sites

| Функция | Передаваемая схема |
|---|---|
| `split_story` | `SplitResponse` |
| `bootstrap_characters` | `CharactersResponse` |
| `build_scene_prompt` (Flash и Pro вызовы) | `ScenePromptResponse` |
| `generate_design_spec` | `DesignSpec` |

### 3.4 Batch path (`batch_collect_scene_prompts`)

Batch API не проходит через `call_llm_json` и re-prompt в batch невозможен (stateless). Валидация делается в месте разбора ответа:

```python
try:
    data = ScenePromptResponse.model_validate(
        _parse_batch_response_text(resp_text)
    ).model_dump()
except ValidationError as ve:
    log.error("Batch scene %d schema fail: %s", scene.index, ve)
    scene.status = "error"
    scene.error = f"schema: {ve}"
    continue
```

Сцены с fail-validation помечаются `status=error` — `--resume` в realtime-режиме подберёт их и пройдёт через полный retry-цикл с re-prompt.

---

## 4. Data flow

```
LLM call (call_llm_json)
  ├─ generate_content()
  ├─ json.loads() ─── JSONDecodeError ──→ short backoff + retry
  ├─ schema.model_validate()
  │   ├─ success ──→ return .model_dump()
  │   └─ ValidationError ──→ append error to prompt, short backoff, retry
  ├─ API error ──→ classify + backoff (существующая логика)
  └─ MAX_RETRIES exhausted ──→ fallback model (same schema) ──→ RuntimeError
```

---

## 5. Error handling / edge cases

- **Пустой `scenes[]` в split-ответе** — `SplitResponse.scenes` требует `min_length=1`. Fail → retry → RuntimeError при исчерпании бюджета. Пользователь видит ошибку.
- **LLM галлюцинирует `id` с кириллицей** — `pattern=r"^[a-z0-9_]+$"` ловит. Re-prompt исправляет.
- **`subtitle_lines > 42 chars`** — кастомный validator ловит. Закрывает 🟡 из раздела 12 TODO.
- **Неизвестное поле в design_spec** — `extra="allow"` пропускает, не падаем.
- **Накопление error-текста между retry'ами** — предотвращается через фиксацию `base_prompt` до цикла.
- **Deterministic split + validation fail** — модифицированный prompt ломает детерминизм только для retry-attempt. Baseline-попытка остаётся детерминированной. Приемлемо.
- **Batch: re-prompt невозможен** — сцена помечается `error`, подбирается `--resume` в realtime-режиме.

---

## 6. Testing plan

### 6.1 `tests/conftest.py`

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
```

Позволяет импортировать `generate_comic` и `schemas` из корня без packaging.

### 6.2 `tests/test_pure.py`

Для каждой из 5 функций — `@pytest.mark.parametrize` матрицы:

**`classify_error`:**
- Исключение с сообщением содержащим `"429"` → `("rate_limit", None)`
- То же + `"retryDelay: 30"` в тексте → `("rate_limit", 30.0)` (regex парсит из сообщения, а не из HTTP-заголовка)
- Сообщение `"503 UNAVAILABLE"` → `("overload", None)`
- `"500 INTERNAL"` / `"502 BAD_GATEWAY"` → `("server", None)`
- `"504"` / `"DEADLINE_EXCEEDED"` → `("timeout", None)` (504 в `RETRYABLE_STATUSES` маппится на `timeout`, не `server`)
- `"400 INVALID_ARGUMENT"` / `"401"` / `"403 PERMISSION_DENIED"` / `"404"` → `("fatal", None)`
- `"TIMEOUT"` в сообщении → `("timeout", None)` (проверить через `RETRYABLE_STATUSES` mapping)
- `RuntimeError("boom")` без кодов → `("unknown", None)`

Точный набор кодов — читать из констант `FATAL_STATUSES` и `RETRYABLE_STATUSES` в `generate_comic.py`.

**`backoff_delay`:**
- Три `attempt` значения × 4 `kind` — проверяем нижнюю границу (0) и верхнюю (cap: 300 для overload/rate_limit, 120 для 5xx).
- `retry_after=30` — результат не меньше 30, не больше cap.

**`_fmt_srt_time`:**
- `0.0` → `"00:00:00,000"`
- `3661.5` → `"01:01:01,500"`
- `7200.001` → `"02:00:00,001"`

**`estimate_duration`:**
- Одинаковый текст под `slow` / `normal` / `fast` — `slow > normal > fast`.
- Пустая строка → минимум (1 слово).

**`pick_scene_model`:**
- `force_pro=True` → `PRO_MODEL` безусловно.
- `expected_chars >= COMPLEX_SCENE_CHAR_THRESHOLD` → `PRO_MODEL`.
- Длинный `scene_text` (>=900 символов) → `PRO_MODEL`.
- Простой короткий случай → `FLASH_MODEL`.

### 6.3 `tests/test_schemas.py`

Для каждой из 4 моделей — минимум:

- **Happy path:** валидный JSON из примеров README / system-prompt'а.
- **2-3 invalid:** пустое required-поле, несоответствие pattern, out-of-bounds, невалидный enum.
- **`extra="allow"` проверка:** неизвестное поле не ломает валидацию.
- Для `ScenePromptResponse`: явный тест на `pacing` enum и `subtitle_lines` length validator.

### 6.4 Запуск

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## 7. Import safety

**Проверено:** `generate_comic.py` при импорте безопасен — `genai.Client()` создаётся только внутри `main()`, env-проверка `GEMINI_API_KEY` тоже внутри `main()`. `load_dotenv()` на top-level работает молча даже без `.env`.

Для импорта в тестах дополнительные правки `generate_comic.py` не требуются. `conftest.py` просто добавляет корень в `sys.path`.

---

## 8. Dependencies

**Добавляется:** `pytest>=8.0` в `requirements-dev.txt`.
**Не добавляется:** `pydantic` уже в дереве зависимостей (транзитивная dep `google-genai`, версия 2.13.2).

---

## 9. Success criteria

1. `pytest tests/ -v` — все тесты зелёные.
2. `python generate_comic.py --story story.txt --dry-run --bootstrap` — отрабатывает как до изменений.
3. Искусственный подстановочный тест (ручной): подсунуть через mock ответ с невалидным `pacing` — retry-цикл выдаёт re-prompt с error-текстом; при исчерпании `MAX_RETRIES` — `RuntimeError`.
4. Никакие существующие функции-потребители не требуют правок (все `data.get(...)` работают поверх `.model_dump()`).

---

## 10. Out of scope / следующие specы

| Feature | Куда |
|---|---|
| Integration-тест с моknutым `genai.Client` | 2026-xx-xx-integration-tests-design.md |
| Golden-тест для SRT | same as above |
| Retry-бюджет с предохранителем | 2026-xx-xx-retry-budget-design.md |
| Chaos-тесты | together with integration |
| Coverage reporting / CI | 2026-xx-xx-ci-setup-design.md |

---

## 11. Risks

- **Pydantic-drift:** pydantic 2.13 → 3.x breaking changes возможны. Риск низкий — API `model_validate` / `model_dump` стабильны с 2.0.
- **Schema слишком строгая:** если LLM действительно начнёт выдавать что-то вне enum/pattern регулярно — будем расширять схему в ответ на реальные данные, не наперёд.
- **Детерминизм в split:** одна validation-retry делает prompt не-detвrministic только внутри этой попытки. Влияние на reproducibility split минимальное.
