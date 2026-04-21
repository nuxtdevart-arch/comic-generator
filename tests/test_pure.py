"""Characterization tests for pure functions in generate_comic."""
import pytest

from generate_comic import (
    backoff_delay, classify_error, _fmt_srt_time,
    estimate_duration, MIN_SCENE_DURATION, MAX_SCENE_DURATION,
    pick_scene_model, FLASH_MODEL, PRO_MODEL,
    COMPLEX_SCENE_CHAR_THRESHOLD, COMPLEX_SCENE_LENGTH_CHARS,
)


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


from generate_comic import effective_duration, Scene


class TestEffectiveDuration:
    def test_uses_audio_duration_when_present(self):
        s = Scene(index=1, text="x", voice_text="hello", audio_duration=3.5)
        assert effective_duration(s) == 3.5

    def test_fallback_when_audio_duration_zero(self):
        s = Scene(index=1, text="x", voice_text="hello", audio_duration=0.0)
        # fallback идёт в estimate_duration → > MIN_SCENE_DURATION
        assert effective_duration(s) >= MIN_SCENE_DURATION

    def test_fallback_when_no_voice_text(self):
        s = Scene(index=1, text="fallback text", voice_text="")
        # estimate_duration на scene.text
        assert effective_duration(s) >= MIN_SCENE_DURATION

    def test_audio_duration_wins_even_if_duration_sec_set(self):
        s = Scene(index=1, text="x", voice_text="hello",
                  duration_sec=10.0, audio_duration=2.2)
        assert effective_duration(s) == 2.2
