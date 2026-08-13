"""Tests for ui/server/rate_limit.py's per-session_id token bucket."""

from unittest.mock import patch

from ui.server import rate_limit
from ui.server.rate_limit import allow


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
