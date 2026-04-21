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
