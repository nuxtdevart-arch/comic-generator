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
