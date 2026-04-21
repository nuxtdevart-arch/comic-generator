"""Pydantic schemas for LLM JSON responses.

Used by call_llm_json to validate and re-prompt on ValidationError.
Models have extra='allow' so the LLM can add fields without breaking us.
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


# ── 1. split_story ───────────────────────────────────────────────────
class SplitScene(_Base):
    text: str = Field(min_length=1)
    title: str = ""


class SplitResponse(_Base):
    scenes: list[SplitScene] = Field(min_length=1)


# ── 2. bootstrap_characters ──────────────────────────────────────────
class BootstrapCharacter(_Base):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class CharactersResponse(_Base):
    characters: list[BootstrapCharacter]


# -- 3. build_scene_prompt (realtime and batch) -----------------------
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
