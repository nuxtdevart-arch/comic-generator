"""Unit tests for video.py pure helpers."""
import pytest

from video import _fmt_ass_time, _hex_to_ass_color


class TestFmtAssTime:
    @pytest.mark.parametrize("seconds,expected", [
        (0.0, "0:00:00.00"),
        (3.456, "0:00:03.46"),
        (59.999, "0:01:00.00"),
        (60.0, "0:01:00.00"),
        (3661.5, "1:01:01.50"),
        (28.26448979, "0:00:28.26"),
    ])
    def test_format(self, seconds, expected):
        assert _fmt_ass_time(seconds) == expected


class TestHexToAssColor:
    @pytest.mark.parametrize("hex_in,ass_out", [
        ("#FF0000", "&H000000FF"),  # red  (BGR + alpha)
        ("#00FF00", "&H0000FF00"),  # green
        ("#0000FF", "&H00FF0000"),  # blue
        ("#FFFFFF", "&H00FFFFFF"),  # white
        ("#000000", "&H00000000"),  # black
        ("#F0F0F0", "&H00F0F0F0"),  # design_spec default color_fg
        ("F0F0F0",  "&H00F0F0F0"),  # no leading #
    ])
    def test_conversion(self, hex_in, ass_out):
        assert _hex_to_ass_color(hex_in) == ass_out

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _hex_to_ass_color("not-a-color")
