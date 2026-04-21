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
