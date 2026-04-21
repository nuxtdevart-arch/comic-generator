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

from schemas import ScenePromptResponse


SCENE_OK = {
    "existing_character_ids": ["aleksey_38"],
    "new_characters": [],
    "prompt": "cinematic english paragraph",
    "voice_text": "??????? ?????",
    "speaker": "narrator",
    "emotion": "melancholic",
    "pacing": "normal",
    "subtitle_lines": ["?????? 1", "?????? 2"],
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
