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
