# Unit Tests + LLM Schema Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить pytest-покрытие 5 чистых функций и pydantic-валидацию для 4 LLM-ответов с retry-on-validation-fail.

**Architecture:** Новый `schemas.py` (pydantic-модели), новая папка `tests/` (pytest), патч `call_llm_json` принимает параметр `schema` и переспрашивает LLM на `ValidationError`. Batch path валидирует в call-site, помечая сцены `status=error` при fail.

**Tech Stack:** Python 3.14, pytest 8.x, pydantic 2.13 (уже в деревe deps от google-genai).

**Spec:** `docs/superpowers/specs/2026-04-21-tests-schema-validation-design.md`

---

## File Structure

**Создаются:**
- `schemas.py` — pydantic-модели (`SplitResponse`, `CharactersResponse`, `ScenePromptResponse`, `DesignSpec` + вложенные).
- `tests/__init__.py` — пустой маркер.
- `tests/conftest.py` — `sys.path` shim для импорта из root.
- `tests/test_pure.py` — тесты `classify_error`, `backoff_delay`, `_fmt_srt_time`, `estimate_duration`, `pick_scene_model`.
- `tests/test_schemas.py` — happy + invalid кейсы для 4 моделей.
- `requirements-dev.txt` — `pytest>=8.0`.
- `.gitignore` — Python standard + `output/`, `references/`, `.env`, `__pycache__/`.

**Модифицируются:**
- `generate_comic.py`:
  - Добавить `from schemas import ...`, `from pydantic import BaseModel, ValidationError`.
  - `call_llm_json` (строки 185–258) — новый параметр `schema`, валидация в retry-loop.
  - `split_story` (299) — передать `schema=SplitResponse`.
  - `bootstrap_characters` (608) — передать `schema=CharactersResponse`.
  - `build_scene_prompt` (385) — передать `schema=ScenePromptResponse` в оба вызова.
  - `generate_design_spec` (717) — передать `schema=DesignSpec`.
  - `batch_collect_scene_prompts` (483) — валидировать через `ScenePromptResponse.model_validate` в call-site.

---

## Task 0: Git init + gitignore

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Initialize repository**

```bash
git init
git branch -M main
```

- [ ] **Step 2: Create .gitignore**

Write to `.gitignore`:

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.pytest_cache/

# Project
.env
output/
references/
*.png
!docs/**/*.png

# IDE
.vscode/
.idea/
```

- [ ] **Step 3: Initial commit of existing project**

```bash
git add .gitignore generate_comic.py README.md TODO.md story.txt characters.json docs/
git commit -m "chore: initial repo with existing script"
```

Expected: первый коммит создан.

---

## Task 1: Add dev dependencies

**Files:**
- Create: `requirements-dev.txt`

- [ ] **Step 1: Write requirements-dev.txt**

```
pytest>=8.0
```

- [ ] **Step 2: Install**

```bash
pip install -r requirements-dev.txt
```

Expected: `pytest` установлен. Проверка:

```bash
pytest --version
```

Expected: `pytest 8.x.x`

- [ ] **Step 3: Commit**

```bash
git add requirements-dev.txt
git commit -m "chore: add pytest dev dependency"
```

---

## Task 2: Tests skeleton

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create empty package marker**

Write to `tests/__init__.py`:

```python
```

(Пустой файл.)

- [ ] **Step 2: Create conftest with sys.path shim**

Write to `tests/conftest.py`:

```python
"""Allow tests to import modules from project root (generate_comic, schemas)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [ ] **Step 3: Verify pytest discovers the tests folder**

```bash
pytest tests/ --collect-only
```

Expected: `no tests ran in 0.XXs` (папка пустая, но найдена без ошибок).

- [ ] **Step 4: Commit**

```bash
git add tests/__init__.py tests/conftest.py
git commit -m "test: add pytest skeleton with sys.path shim"
```

---

## Task 3: schemas.py — SplitResponse (TDD)

**Files:**
- Create: `schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Write failing test**

Write to `tests/test_schemas.py`:

```python
"""Tests for LLM response schemas."""
import pytest
from pydantic import ValidationError

from schemas import SplitResponse


class TestSplitResponse:
    def test_happy_path(self):
        data = {"scenes": [
            {"title": "Bathroom 3am", "text": "3 часа ночи."},
            {"title": "", "text": "Тишина."},
        ]}
        result = SplitResponse.model_validate(data)
        assert len(result.scenes) == 2
        assert result.scenes[0].title == "Bathroom 3am"

    def test_empty_scenes_rejected(self):
        with pytest.raises(ValidationError):
            SplitResponse.model_validate({"scenes": []})

    def test_missing_text_rejected(self):
        with pytest.raises(ValidationError):
            SplitResponse.model_validate({"scenes": [{"title": "x"}]})

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            SplitResponse.model_validate({"scenes": [{"text": ""}]})

    def test_extra_field_allowed(self):
        data = {"scenes": [{"text": "t"}], "extra_meta": "ignored"}
        result = SplitResponse.model_validate(data)
        assert len(result.scenes) == 1
```

- [ ] **Step 2: Run test, verify it fails**

```bash
pytest tests/test_schemas.py -v
```

Expected: `ModuleNotFoundError: No module named 'schemas'`

- [ ] **Step 3: Create schemas.py with SplitResponse**

Write to `schemas.py`:

```python
"""Pydantic schemas for LLM JSON responses.

Used by call_llm_json to validate and re-prompt on ValidationError.
Models have extra='allow' so the LLM can add fields without breaking us.
"""
from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


# ── 1. split_story ───────────────────────────────────────────────────
class SplitScene(_Base):
    text: str = Field(min_length=1)
    title: str = ""


class SplitResponse(_Base):
    scenes: list[SplitScene] = Field(min_length=1)
```

- [ ] **Step 4: Run test, verify it passes**

```bash
pytest tests/test_schemas.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add schemas.py tests/test_schemas.py
git commit -m "feat(schemas): SplitResponse with tests"
```

---

## Task 4: schemas.py — CharactersResponse (TDD)

**Files:**
- Modify: `schemas.py`
- Modify: `tests/test_schemas.py`

- [ ] **Step 1: Append failing test**

Append to `tests/test_schemas.py`:

```python
from schemas import CharactersResponse


class TestCharactersResponse:
    def test_happy_path(self):
        data = {"characters": [
            {"id": "aleksey_38", "name": "Алексей", "description": "38-year-old man..."},
        ]}
        result = CharactersResponse.model_validate(data)
        assert result.characters[0].id == "aleksey_38"

    def test_empty_characters_ok(self):
        result = CharactersResponse.model_validate({"characters": []})
        assert result.characters == []

    def test_cyrillic_id_rejected(self):
        with pytest.raises(ValidationError):
            CharactersResponse.model_validate({"characters": [
                {"id": "Алексей-38", "name": "x", "description": "y"},
            ]})

    def test_uppercase_id_rejected(self):
        with pytest.raises(ValidationError):
            CharactersResponse.model_validate({"characters": [
                {"id": "AleksEy_38", "name": "x", "description": "y"},
            ]})

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            CharactersResponse.model_validate({"characters": [
                {"id": "x", "name": "", "description": "y"},
            ]})
```

- [ ] **Step 2: Run test, verify it fails**

```bash
pytest tests/test_schemas.py::TestCharactersResponse -v
```

Expected: `ImportError: cannot import name 'CharactersResponse'`

- [ ] **Step 3: Append to schemas.py**

Append to `schemas.py`:

```python


# ── 2. bootstrap_characters ──────────────────────────────────────────
class BootstrapCharacter(_Base):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class CharactersResponse(_Base):
    characters: list[BootstrapCharacter]
```

- [ ] **Step 4: Run all schema tests**

```bash
pytest tests/test_schemas.py -v
```

Expected: 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add schemas.py tests/test_schemas.py
git commit -m "feat(schemas): CharactersResponse with tests"
```

---

## Task 5: schemas.py — ScenePromptResponse (TDD)

**Files:**
- Modify: `schemas.py`
- Modify: `tests/test_schemas.py`

- [ ] **Step 1: Append failing test**

Append to `tests/test_schemas.py`:

```python
from schemas import ScenePromptResponse


SCENE_OK = {
    "existing_character_ids": ["aleksey_38"],
    "new_characters": [],
    "prompt": "cinematic english paragraph",
    "voice_text": "русский текст",
    "speaker": "narrator",
    "emotion": "melancholic",
    "pacing": "normal",
    "subtitle_lines": ["строка 1", "строка 2"],
}


class TestScenePromptResponse:
    def test_happy_path(self):
        result = ScenePromptResponse.model_validate(SCENE_OK)
        assert result.pacing == "normal"
        assert len(result.subtitle_lines) == 2

    def test_defaults(self):
        minimal = {
            "prompt": "p",
            "voice_text": "v",
            "subtitle_lines": ["one"],
        }
        result = ScenePromptResponse.model_validate(minimal)
        assert result.speaker == "narrator"
        assert result.pacing == "normal"
        assert result.existing_character_ids == []

    def test_bad_pacing_rejected(self):
        bad = dict(SCENE_OK, pacing="turbo")
        with pytest.raises(ValidationError, match="pacing"):
            ScenePromptResponse.model_validate(bad)

    def test_subtitle_line_too_long_rejected(self):
        bad = dict(SCENE_OK, subtitle_lines=["x" * 43])
        with pytest.raises(ValidationError, match="42"):
            ScenePromptResponse.model_validate(bad)

    def test_subtitle_exactly_42_chars_ok(self):
        ok = dict(SCENE_OK, subtitle_lines=["x" * 42])
        result = ScenePromptResponse.model_validate(ok)
        assert result.subtitle_lines[0] == "x" * 42

    def test_empty_subtitle_lines_rejected(self):
        bad = dict(SCENE_OK, subtitle_lines=[])
        with pytest.raises(ValidationError):
            ScenePromptResponse.model_validate(bad)

    def test_four_subtitle_lines_rejected(self):
        bad = dict(SCENE_OK, subtitle_lines=["a", "b", "c", "d"])
        with pytest.raises(ValidationError):
            ScenePromptResponse.model_validate(bad)

    def test_empty_prompt_rejected(self):
        bad = dict(SCENE_OK, prompt="")
        with pytest.raises(ValidationError):
            ScenePromptResponse.model_validate(bad)

    def test_new_character_bad_id(self):
        bad = dict(SCENE_OK, new_characters=[
            {"id": "Bad-ID", "name": "x", "description": "y"},
        ])
        with pytest.raises(ValidationError):
            ScenePromptResponse.model_validate(bad)

    def test_all_pacing_values(self):
        for p in ("slow", "normal", "fast"):
            result = ScenePromptResponse.model_validate(dict(SCENE_OK, pacing=p))
            assert result.pacing == p
```

- [ ] **Step 2: Run test, verify it fails**

```bash
pytest tests/test_schemas.py::TestScenePromptResponse -v
```

Expected: `ImportError: cannot import name 'ScenePromptResponse'`

- [ ] **Step 3: Update imports in schemas.py**

Найди в `schemas.py` строку:

```python
from pydantic import BaseModel, ConfigDict, Field
```

Замени на:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator
```

- [ ] **Step 4: Append models to schemas.py**

Append to `schemas.py`:

```python


# ── 3. build_scene_prompt (realtime and batch) ───────────────────────
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
    def _validate_pacing(cls, v: str) -> str:
        if v not in {"slow", "normal", "fast"}:
            raise ValueError(f"pacing must be slow|normal|fast, got {v!r}")
        return v

    @field_validator("subtitle_lines")
    @classmethod
    def _validate_subtitle_lines(cls, v: list[str]) -> list[str]:
        for line in v:
            if len(line) > 42:
                raise ValueError(f"subtitle line exceeds 42 chars: {line!r}")
        return v
```

- [ ] **Step 5: Run all schema tests**

```bash
pytest tests/test_schemas.py -v
```

Expected: 20 tests pass.

- [ ] **Step 6: Commit**

```bash
git add schemas.py tests/test_schemas.py
git commit -m "feat(schemas): ScenePromptResponse with pacing/subtitle validators"
```

---

## Task 6: schemas.py — DesignSpec (TDD)

**Files:**
- Modify: `schemas.py`
- Modify: `tests/test_schemas.py`

- [ ] **Step 1: Append failing test**

Append to `tests/test_schemas.py`:

```python
from schemas import DesignSpec


DESIGN_OK = {
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
    "rationale": "high contrast for Soviet comic-noir",
}


class TestDesignSpec:
    def test_happy_path(self):
        result = DesignSpec.model_validate(DESIGN_OK)
        assert result.font_family == "PT Sans Narrow"
        assert result.color_bg_gradient == ["#000000CC", "#00000000"]

    def test_color_without_hash_rejected(self):
        bad = dict(DESIGN_OK, color_fg="E8C77D")
        with pytest.raises(ValidationError):
            DesignSpec.model_validate(bad)

    def test_color_too_short_rejected(self):
        bad = dict(DESIGN_OK, color_fg="#ABC")
        with pytest.raises(ValidationError):
            DesignSpec.model_validate(bad)

    def test_weight_out_of_range(self):
        bad = dict(DESIGN_OK, font_weight=1000)
        with pytest.raises(ValidationError):
            DesignSpec.model_validate(bad)

    def test_size_out_of_range(self):
        bad = dict(DESIGN_OK, font_size_px=5)
        with pytest.raises(ValidationError):
            DesignSpec.model_validate(bad)

    def test_gradient_single_color_rejected(self):
        bad = dict(DESIGN_OK, color_bg_gradient=["#000000CC"])
        with pytest.raises(ValidationError):
            DesignSpec.model_validate(bad)

    def test_gradient_three_colors_rejected(self):
        bad = dict(DESIGN_OK, color_bg_gradient=["#111", "#222", "#333"])
        with pytest.raises(ValidationError):
            DesignSpec.model_validate(bad)

    def test_margin_out_of_range(self):
        bad = dict(DESIGN_OK, margin_bottom_pct=80)
        with pytest.raises(ValidationError):
            DesignSpec.model_validate(bad)

    def test_stroke_negative_rejected(self):
        bad = dict(DESIGN_OK, stroke_px=-1)
        with pytest.raises(ValidationError):
            DesignSpec.model_validate(bad)

    def test_extra_field_allowed(self):
        ok = dict(DESIGN_OK, letter_spacing_px=1.5)
        result = DesignSpec.model_validate(ok)
        assert result.font_family == "PT Sans Narrow"
```

- [ ] **Step 2: Run test, verify it fails**

```bash
pytest tests/test_schemas.py::TestDesignSpec -v
```

Expected: `ImportError: cannot import name 'DesignSpec'`

- [ ] **Step 3: Append to schemas.py**

Append to `schemas.py`:

```python


# ── 4. design_spec ───────────────────────────────────────────────────
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

- [ ] **Step 4: Run all schema tests**

```bash
pytest tests/test_schemas.py -v
```

Expected: 30 tests pass.

- [ ] **Step 5: Commit**

```bash
git add schemas.py tests/test_schemas.py
git commit -m "feat(schemas): DesignSpec with range/pattern validators"
```

---

## Task 7: test_pure.py — classify_error (characterization tests)

**Files:**
- Create: `tests/test_pure.py`

- [ ] **Step 1: Write failing test**

Write to `tests/test_pure.py`:

```python
"""Characterization tests for pure functions in generate_comic."""
import pytest

from generate_comic import classify_error


class TestClassifyError:
    @pytest.mark.parametrize("msg,expected_kind", [
        ("429 RESOURCE_EXHAUSTED", "rate_limit"),
        ("503 UNAVAILABLE", "overload"),
        ("500 INTERNAL", "server"),
        ("502 Bad Gateway", "server"),
        ("504 DEADLINE_EXCEEDED", "timeout"),
        ("400 INVALID_ARGUMENT", "fatal"),
        ("401 Unauthorized", "fatal"),
        ("403 PERMISSION_DENIED", "fatal"),
        ("404 NOT_FOUND", "fatal"),
        ("some completely unrelated message", "unknown"),
    ])
    def test_status_mapping(self, msg, expected_kind):
        kind, _ = classify_error(RuntimeError(msg))
        assert kind == expected_kind

    def test_fatal_takes_priority_over_retryable(self):
        # 400 fatal substring wins even when message also contains 429-ish text
        kind, _ = classify_error(RuntimeError("400 INVALID_ARGUMENT (also 429)"))
        assert kind == "fatal"

    def test_retry_after_from_retry_delay(self):
        err = RuntimeError('{"error": {"retryDelay": 30}} 429')
        kind, retry_after = classify_error(err)
        assert kind == "rate_limit"
        assert retry_after == 30.0

    def test_retry_after_from_trailing_seconds(self):
        err = RuntimeError('{"retry": "42s"} 429')
        kind, retry_after = classify_error(err)
        assert kind == "rate_limit"
        assert retry_after == 42.0

    def test_no_retry_after_when_not_present(self):
        _, retry_after = classify_error(RuntimeError("503 UNAVAILABLE"))
        assert retry_after is None
```

- [ ] **Step 2: Run test, verify it passes**

Характеризационный тест — функция уже работает, тест просто фиксирует поведение.

```bash
pytest tests/test_pure.py::TestClassifyError -v
```

Expected: 14 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pure.py
git commit -m "test: classify_error characterization tests"
```

---

## Task 8: test_pure.py — backoff_delay

**Files:**
- Modify: `tests/test_pure.py`

- [ ] **Step 1: Append test**

Append to `tests/test_pure.py`:

```python
from generate_comic import backoff_delay


class TestBackoffDelay:
    def test_retry_after_honored_with_jitter(self):
        delays = [backoff_delay(0, "rate_limit", retry_after=30) for _ in range(20)]
        # Jitter is +0.5 to +3.0 seconds on top of retry_after
        assert all(30.5 <= d <= 33.0 for d in delays)

    def test_overload_grows_exponentially(self):
        # With no retry_after, bounded between base and exp(cap)
        d0 = [backoff_delay(0, "overload") for _ in range(30)]
        d3 = [backoff_delay(3, "overload") for _ in range(30)]
        # Higher attempt means higher upper bound
        assert max(d3) > max(d0)

    def test_overload_cap_is_300(self):
        # Cap for overload/rate_limit is 300s
        delays = [backoff_delay(20, "overload") for _ in range(30)]
        assert all(d <= 300.0 for d in delays)

    def test_server_cap_is_120(self):
        # Cap for non-overload kinds is 120s
        delays = [backoff_delay(20, "server") for _ in range(30)]
        assert all(d <= 120.0 for d in delays)

    def test_overload_starts_higher_than_server(self):
        # base * 4 for overload means average delay is higher
        over = [backoff_delay(0, "overload") for _ in range(100)]
        serv = [backoff_delay(0, "server") for _ in range(100)]
        assert sum(over) / len(over) > sum(serv) / len(serv)

    def test_returns_float(self):
        assert isinstance(backoff_delay(0, "server"), float)
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_pure.py::TestBackoffDelay -v
```

Expected: 6 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pure.py
git commit -m "test: backoff_delay characterization tests"
```

---

## Task 9: test_pure.py — _fmt_srt_time

**Files:**
- Modify: `tests/test_pure.py`

- [ ] **Step 1: Append test**

Append to `tests/test_pure.py`:

```python
from generate_comic import _fmt_srt_time


class TestFmtSrtTime:
    @pytest.mark.parametrize("seconds,expected", [
        (0.0, "00:00:00,000"),
        (1.0, "00:00:01,000"),
        (59.999, "00:00:59,999"),
        (60.0, "00:01:00,000"),
        (3600.0, "01:00:00,000"),
        (3661.5, "01:01:01,500"),
        (7200.001, "02:00:00,001"),
    ])
    def test_formatting(self, seconds, expected):
        assert _fmt_srt_time(seconds) == expected

    def test_output_format_has_comma_separator(self):
        # SRT uses comma, not dot, before milliseconds
        assert "," in _fmt_srt_time(1.234)
        assert "." not in _fmt_srt_time(1.234)
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_pure.py::TestFmtSrtTime -v
```

Expected: 8 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pure.py
git commit -m "test: _fmt_srt_time characterization tests"
```

---

## Task 10: test_pure.py — estimate_duration

**Files:**
- Modify: `tests/test_pure.py`

- [ ] **Step 1: Append test**

Append to `tests/test_pure.py`:

```python
from generate_comic import estimate_duration, MIN_SCENE_DURATION, MAX_SCENE_DURATION


class TestEstimateDuration:
    def test_min_duration_floor(self):
        # Short text clamps to MIN_SCENE_DURATION
        assert estimate_duration("a") >= MIN_SCENE_DURATION

    def test_max_duration_cap(self):
        # Very long text clamps to MAX_SCENE_DURATION
        long_text = "слово " * 500
        assert estimate_duration(long_text) <= MAX_SCENE_DURATION

    def test_pacing_order(self):
        text = "один два три четыре пять шесть семь восемь девять десять"
        slow = estimate_duration(text, "slow")
        normal = estimate_duration(text, "normal")
        fast = estimate_duration(text, "fast")
        assert slow >= normal >= fast

    def test_returns_float(self):
        assert isinstance(estimate_duration("hello world"), float)

    def test_empty_string_uses_min_one_word(self):
        # Implementation guarantees at least 1 word
        result = estimate_duration("")
        assert result >= MIN_SCENE_DURATION
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_pure.py::TestEstimateDuration -v
```

Expected: 5 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pure.py
git commit -m "test: estimate_duration characterization tests"
```

---

## Task 11: test_pure.py — pick_scene_model

**Files:**
- Modify: `tests/test_pure.py`

- [ ] **Step 1: Append test**

Append to `tests/test_pure.py`:

```python
from generate_comic import (
    pick_scene_model, FLASH_MODEL, PRO_MODEL,
    COMPLEX_SCENE_CHAR_THRESHOLD, COMPLEX_SCENE_LENGTH_CHARS,
)


class TestPickSceneModel:
    def test_force_pro_wins(self):
        assert pick_scene_model("short", expected_chars=0, force_pro=True) == PRO_MODEL

    def test_simple_scene_uses_flash(self):
        assert pick_scene_model("short scene", expected_chars=1) == FLASH_MODEL

    def test_many_characters_escalates_to_pro(self):
        assert (
            pick_scene_model("short", expected_chars=COMPLEX_SCENE_CHAR_THRESHOLD)
            == PRO_MODEL
        )

    def test_one_below_threshold_stays_flash(self):
        assert (
            pick_scene_model("short", expected_chars=COMPLEX_SCENE_CHAR_THRESHOLD - 1)
            == FLASH_MODEL
        )

    def test_long_scene_text_escalates_to_pro(self):
        long_text = "x" * COMPLEX_SCENE_LENGTH_CHARS
        assert pick_scene_model(long_text, expected_chars=0) == PRO_MODEL

    def test_short_scene_text_stays_flash(self):
        short = "x" * (COMPLEX_SCENE_LENGTH_CHARS - 1)
        assert pick_scene_model(short, expected_chars=0) == FLASH_MODEL

    def test_force_pro_overrides_simple_scene(self):
        assert pick_scene_model("x", expected_chars=0, force_pro=True) == PRO_MODEL
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_pure.py::TestPickSceneModel -v
```

Expected: 7 tests pass.

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```

Expected: 70+ tests pass (все из test_pure.py и test_schemas.py).

- [ ] **Step 4: Commit**

```bash
git add tests/test_pure.py
git commit -m "test: pick_scene_model characterization tests"
```

---

## Task 12: Integrate schema parameter into call_llm_json

**Files:**
- Modify: `generate_comic.py` (строки 185–258, функция `call_llm_json`)

- [ ] **Step 1: Add imports**

Найди в `generate_comic.py` блок импортов (строки 26–37) и добавь после `from typing import Any`:

```python
from pydantic import BaseModel, ValidationError

from schemas import (
    CharactersResponse,
    DesignSpec,
    ScenePromptResponse,
    SplitResponse,
)
```

- [ ] **Step 2: Replace call_llm_json**

Замени всю функцию `call_llm_json` (строки 185–258) на:

```python
def call_llm_json(client: genai.Client, model: str, prompt: str,
                  system: str | None = None,
                  deterministic: bool = False,
                  schema: type[BaseModel] | None = None) -> Any:
    """Call LLM and parse JSON from the response.

    Robust to 429/503/5xx with full-jitter exponential backoff and
    Retry-After honoring. Falls back to a cheaper model after exhausting
    retries.

    If schema is provided, validates the parsed JSON against it. On
    ValidationError, re-prompts the LLM with the error detail attached,
    consuming the retry budget. Returns result.model_dump() so callers
    using data.get(...) keep working unchanged.

    deterministic=True forces temperature=0 and disables thinking.
    """
    cfg_kwargs: dict[str, Any] = {
        "response_mime_type": "application/json",
        "system_instruction": system,
    }
    if deterministic:
        cfg_kwargs["temperature"] = 0.0
        cfg_kwargs["thinking_config"] = genai_types.ThinkingConfig(
            thinking_budget=0,
        )
    cfg = genai_types.GenerateContentConfig(**cfg_kwargs)
    fallback = FLASH_FALLBACK_MODEL if model == FLASH_MODEL else (
        PRO_FALLBACK_MODEL if model == PRO_MODEL else None
    )
    base_prompt = prompt
    current_prompt = base_prompt
    last_err: Exception | None = None
    consec_overload = 0
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.models.generate_content(
                model=model, contents=current_prompt, config=cfg,
            )
            text = (resp.text or "").strip()
            # strip ```json fences just in case
            text = re.sub(r"^```(?:json)?|```$", "", text,
                          flags=re.MULTILINE).strip()
            data = json.loads(text)

            if schema is not None:
                try:
                    return schema.model_validate(data).model_dump()
                except ValidationError as ve:
                    last_err = ve
                    log.warning(
                        "Schema validation failed on %s (attempt %d/%d): %s",
                        model, attempt + 1, MAX_RETRIES + 1, ve,
                    )
                    current_prompt = (
                        base_prompt
                        + "\n\nPREVIOUS RESPONSE FAILED SCHEMA VALIDATION:\n"
                        + str(ve)
                        + "\n\nReturn valid JSON matching the schema exactly."
                    )
                    kind, retry_after = "validation", None
                    consec_overload = 0
                    # fall through to backoff
                else:
                    # pragma: no cover - unreachable, success path returned above
                    pass
            else:
                return data
        except json.JSONDecodeError as e:
            last_err = e
            kind, retry_after = "unknown", None
            consec_overload = 0
            log.warning("LLM returned invalid JSON on %s (attempt %d/%d): %s",
                        model, attempt + 1, MAX_RETRIES + 1, e)
        except Exception as e:
            last_err = e
            kind, retry_after = classify_error(e)
            if kind == "fatal":
                log.error("Fatal API error on %s: %s", model, e)
                raise
            consec_overload = consec_overload + 1 if kind == "overload" else 0
            log.warning("LLM call failed on %s (attempt %d/%d) [%s]: %s",
                        model, attempt + 1, MAX_RETRIES + 1, kind, e)

        # Fast fallback: if model is persistently overloaded, jump early
        # to the fallback model instead of burning more retry budget.
        if consec_overload >= FAST_FALLBACK_OVERLOAD_THRESHOLD and fallback:
            log.warning("%s overloaded x%d, switching to fallback %s early",
                        model, consec_overload, fallback)
            return call_llm_json(client, fallback, base_prompt, system=system,
                                 deterministic=deterministic, schema=schema)

        if attempt >= MAX_RETRIES:
            break
        wait = backoff_delay(attempt, kind, retry_after)
        log.info("Waiting %.1fs before retry...", wait)
        time.sleep(wait)

    if fallback:
        log.warning("All retries exhausted for %s, trying fallback %s",
                    model, fallback)
        return call_llm_json(client, fallback, base_prompt, system=system,
                             deterministic=deterministic, schema=schema)
    raise RuntimeError(f"LLM failed after retries: {last_err}")
```

Ключевые изменения:
- Новый параметр `schema: type[BaseModel] | None = None`
- `base_prompt` сохраняется до цикла, `current_prompt` модифицируется при validation-fail
- Fallback-рекурсия передаёт `schema=schema` и `base_prompt` (не накопленный)

- [ ] **Step 3: Check imports resolve (no tests yet)**

```bash
python -c "import generate_comic"
```

Expected: нет ошибок, модуль импортируется.

- [ ] **Step 4: Verify existing tests still pass**

```bash
pytest tests/ -v
```

Expected: все тесты по-прежнему зелёные (test_pure и test_schemas).

- [ ] **Step 5: Commit**

```bash
git add generate_comic.py
git commit -m "feat(validation): accept schema param in call_llm_json with re-prompt on fail"
```

---

## Task 13: Wire split_story

**Files:**
- Modify: `generate_comic.py` (функция `split_story`, строки 299–311)

- [ ] **Step 1: Update call_llm_json invocation**

Найди:

```python
    data = call_llm_json(client, model,
                         SPLIT_PROMPT.format(story=story),
                         system=SPLIT_SYSTEM,
                         deterministic=True)
```

Замени на:

```python
    data = call_llm_json(client, model,
                         SPLIT_PROMPT.format(story=story),
                         system=SPLIT_SYSTEM,
                         deterministic=True,
                         schema=SplitResponse)
```

- [ ] **Step 2: Verify imports and tests**

```bash
python -c "import generate_comic"
pytest tests/ -v
```

Expected: зелено.

- [ ] **Step 3: Commit**

```bash
git add generate_comic.py
git commit -m "feat(validation): wire SplitResponse into split_story"
```

---

## Task 14: Wire bootstrap_characters

**Files:**
- Modify: `generate_comic.py` (функция `bootstrap_characters`, строки 608–642)

- [ ] **Step 1: Update call_llm_json invocation**

Найди:

```python
    data = call_llm_json(client, model,
                         BOOTSTRAP_PROMPT.format(story=story),
                         system=BOOTSTRAP_SYSTEM,
                         deterministic=True)
```

Замени на:

```python
    data = call_llm_json(client, model,
                         BOOTSTRAP_PROMPT.format(story=story),
                         system=BOOTSTRAP_SYSTEM,
                         deterministic=True,
                         schema=CharactersResponse)
```

- [ ] **Step 2: Verify**

```bash
python -c "import generate_comic"
pytest tests/ -v
```

Expected: зелено.

- [ ] **Step 3: Commit**

```bash
git add generate_comic.py
git commit -m "feat(validation): wire CharactersResponse into bootstrap"
```

---

## Task 15: Wire build_scene_prompt

**Files:**
- Modify: `generate_comic.py` (функция `build_scene_prompt`, строки 385–418)

- [ ] **Step 1: Update both call_llm_json invocations**

Найди первый вызов:

```python
    try:
        data = call_llm_json(client, model, prompt, system=SCENE_SYSTEM)
    except Exception as e:
        if model == FLASH_MODEL and not force_pro:
            log.warning("Flash failed for scene %d, escalating to Pro: %s",
                        scene.index, e)
            data = call_llm_json(client, PRO_MODEL, prompt,
                                 system=SCENE_SYSTEM)
            model = PRO_MODEL
        else:
            raise
```

Замени на:

```python
    try:
        data = call_llm_json(client, model, prompt, system=SCENE_SYSTEM,
                             schema=ScenePromptResponse)
    except Exception as e:
        if model == FLASH_MODEL and not force_pro:
            log.warning("Flash failed for scene %d, escalating to Pro: %s",
                        scene.index, e)
            data = call_llm_json(client, PRO_MODEL, prompt,
                                 system=SCENE_SYSTEM,
                                 schema=ScenePromptResponse)
            model = PRO_MODEL
        else:
            raise
```

Найди второй вызов (после `if n_chars >= COMPLEX_SCENE_CHAR_THRESHOLD ...`):

```python
        data = call_llm_json(client, PRO_MODEL, prompt, system=SCENE_SYSTEM)
```

Замени на:

```python
        data = call_llm_json(client, PRO_MODEL, prompt, system=SCENE_SYSTEM,
                             schema=ScenePromptResponse)
```

- [ ] **Step 2: Verify**

```bash
python -c "import generate_comic"
pytest tests/ -v
```

Expected: зелено.

- [ ] **Step 3: Commit**

```bash
git add generate_comic.py
git commit -m "feat(validation): wire ScenePromptResponse into build_scene_prompt"
```

---

## Task 16: Wire generate_design_spec

**Files:**
- Modify: `generate_comic.py` (функция `generate_design_spec`, строки 717–731)

- [ ] **Step 1: Update call_llm_json invocation**

Найди:

```python
    data = call_llm_json(client, model,
                         DESIGN_SPEC_PROMPT.format(
                             excerpt=story[:2000],
                             style=STYLE_SUFFIX),
                         system=DESIGN_SPEC_SYSTEM,
                         deterministic=True)
```

Замени на:

```python
    data = call_llm_json(client, model,
                         DESIGN_SPEC_PROMPT.format(
                             excerpt=story[:2000],
                             style=STYLE_SUFFIX),
                         system=DESIGN_SPEC_SYSTEM,
                         deterministic=True,
                         schema=DesignSpec)
```

- [ ] **Step 2: Verify**

```bash
python -c "import generate_comic"
pytest tests/ -v
```

Expected: зелено.

- [ ] **Step 3: Commit**

```bash
git add generate_comic.py
git commit -m "feat(validation): wire DesignSpec into generate_design_spec"
```

---

## Task 17: Wire batch path (in-place validation)

**Files:**
- Modify: `generate_comic.py` (функция `batch_collect_scene_prompts`, цикл по ответам, строки 511–519)

**Контекст:** `batch_collect_scene_prompts` возвращает `dict[int, tuple[dict | None, str, str | None]]` вида `{scene_index: (data, model, error)}`. При ошибке парсинга сейчас пишется `(None, model, "parse failed: ...")`. Добавляем validation-step с тем же паттерном.

- [ ] **Step 1: Update the results loop**

Найди:

```python
    for scene, resp in zip(pending, responses):
        if getattr(resp, "error", None):
            results[scene.index] = (None, model, str(resp.error))
            continue
        try:
            data = _parse_batch_response_text(resp.response.text)
            results[scene.index] = (data, model, None)
        except Exception as e:
            results[scene.index] = (None, model, f"parse failed: {e}")
    return results
```

Замени на:

```python
    for scene, resp in zip(pending, responses):
        if getattr(resp, "error", None):
            results[scene.index] = (None, model, str(resp.error))
            continue
        try:
            raw_data = _parse_batch_response_text(resp.response.text)
        except Exception as e:
            results[scene.index] = (None, model, f"parse failed: {e}")
            continue
        try:
            data = ScenePromptResponse.model_validate(raw_data).model_dump()
        except ValidationError as ve:
            log.error("Batch scene %d schema fail: %s", scene.index, ve)
            results[scene.index] = (None, model, f"schema: {ve}")
            continue
        results[scene.index] = (data, model, None)
    return results
```

Сцена с невалидным JSON (parse fail) или невалидной структурой (schema fail) получает `error` в кортеже. Вызывающая сторона уже обрабатывает `error != None` — сцена пометится `status=error`, `--resume` в realtime-режиме пройдёт через re-prompt.

- [ ] **Step 2: Verify**

```bash
python -c "import generate_comic"
pytest tests/ -v
```

Expected: зелено.

- [ ] **Step 3: Commit**

```bash
git add generate_comic.py
git commit -m "feat(validation): batch path marks scene as error on schema fail"
```

---

## Task 18: Smoke test — dry-run pipeline

**Files:**
- (проверка, без изменений кода)

- [ ] **Step 1: Run dry-run pipeline end-to-end**

```bash
python generate_comic.py --story story.txt --bootstrap --batch --dry-run --limit 3
```

Expected:
- Пайплайн проходит bootstrap, split, design spec, batch без ошибок валидации.
- В `progress.json` появляется 3 сцены.
- Никаких `ValidationError` в логе.

Если валидация падает на настоящих данных — значит схема слишком строгая; посмотри лог, ослабь ограничение или расширь enum/pattern по факту наблюдаемых данных.

- [ ] **Step 2: Inspect output**

```bash
cat output/progress.json | head -50
cat output/design_spec.json
```

Expected: валидные JSON, поля соответствуют моделям.

- [ ] **Step 3: Final full test run**

```bash
pytest tests/ -v
```

Expected: все тесты зелёные.

- [ ] **Step 4: Final commit (documentation update)**

Если по ходу работы появились заметки или обновления README — закоммить их. Иначе — готово.

```bash
git status
```

Expected: чистое дерево.

---

## Success Criteria (final)

- [ ] `pytest tests/ -v` — 70+ тестов зелёные.
- [ ] `python generate_comic.py --story story.txt --dry-run --bootstrap --limit 3` — проходит без ValidationError.
- [ ] В `generate_comic.py` все 4 LLM-вызова передают `schema=...`.
- [ ] Batch path помечает сцену `error` при schema fail.
- [ ] Все коммиты атомарные, каждый проходит `pytest`.
