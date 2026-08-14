"""Tests for ui/server/rate_limit.py's per-session_id token bucket."""

from unittest.mock import patch

import pytest

from ui.server import rate_limit
from ui.server.rate_limit import allow, retry_after


class TestAllow:
    def setup_method(self):
        rate_limit._buckets.clear()

    def test_allows_up_to_capacity_then_blocks(self):
        for _ in range(rate_limit.CAPACITY):
            assert allow("s1") is True
        assert allow("s1") is False

    def test_sessions_are_independent(self):
        for _ in range(rate_limit.CAPACITY):
            assert allow("s1") is True
        assert allow("s1") is False
        assert allow("s2") is True

    def test_refills_over_time(self):
        with patch("ui.server.rate_limit.time.monotonic", return_value=0.0):
            for _ in range(rate_limit.CAPACITY):
                assert allow("s1") is True
            assert allow("s1") is False

        with patch("ui.server.rate_limit.time.monotonic", return_value=rate_limit.REFILL_SECONDS):
            assert allow("s1") is True
            assert allow("s1") is False

    def test_tokens_never_exceed_capacity(self):
        with patch("ui.server.rate_limit.time.monotonic", return_value=0.0):
            allow("s1")  # creates the bucket, consumes one token

        with patch(
            "ui.server.rate_limit.time.monotonic", return_value=1000 * rate_limit.REFILL_SECONDS
        ):
            allow("s1")  # a huge elapsed gap must cap the refill, not overshoot

        assert rate_limit._buckets["s1"].tokens == rate_limit.CAPACITY - 1


class TestRetryAfter:
    def setup_method(self):
        rate_limit._buckets.clear()

    def test_zero_when_a_token_is_available(self):
        assert retry_after("fresh-session") == 0.0

    def test_zero_when_the_bucket_still_has_tokens(self):
        allow("s1")
        assert retry_after("s1") == 0.0

    def test_positive_wait_once_the_bucket_is_exhausted(self):
        with patch("ui.server.rate_limit.time.monotonic", return_value=0.0):
            for _ in range(rate_limit.CAPACITY):
                allow("s1")
            assert allow("s1") is False
            wait = retry_after("s1")

        assert wait == rate_limit.REFILL_SECONDS

    def test_wait_shrinks_as_time_passes_without_consuming_a_token(self):
        with patch("ui.server.rate_limit.time.monotonic", return_value=0.0):
            for _ in range(rate_limit.CAPACITY):
                allow("s1")

        with patch(
            "ui.server.rate_limit.time.monotonic", return_value=rate_limit.REFILL_SECONDS / 2
        ):
            wait = retry_after("s1")
            # Read-only: doesn't consume the token it's reporting on.
            assert allow("s1") is False

        assert wait == pytest.approx(rate_limit.REFILL_SECONDS / 2)

    def test_never_negative_once_fully_refilled(self):
        with patch("ui.server.rate_limit.time.monotonic", return_value=0.0):
            for _ in range(rate_limit.CAPACITY):
                allow("s1")

        with patch(
            "ui.server.rate_limit.time.monotonic", return_value=1000 * rate_limit.REFILL_SECONDS
        ):
            assert retry_after("s1") == 0.0
