"""Tests for agent/tools/_errors.py.

This decorator is the agent's honesty/resilience boundary: a tool failure
must become a result the model can react to, not an unhandled exception
that aborts the whole run. See docs/RUNBOOK.md and the module docstring.
"""

import pytest

from agent.tools._errors import reports_index_errors


class TestReportsIndexErrors:
    def test_passes_through_a_successful_call(self):
        @reports_index_errors
        def ok(x):
            return [{"value": x}]

        assert ok(5) == [{"value": 5}]

    def test_catches_any_exception_and_returns_error_row(self):
        @reports_index_errors
        def boom():
            raise ConnectionError("timed out")

        assert boom() == [{"error": "The footage index is unreachable (ConnectionError)."}]

    def test_catches_exceptions_of_arbitrary_type(self):
        @reports_index_errors
        def boom():
            raise ValueError("bad row")

        assert boom() == [{"error": "The footage index is unreachable (ValueError)."}]

    def test_does_not_swallow_baseexception_like_keyboardinterrupt(self):
        @reports_index_errors
        def interrupt():
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            interrupt()

    def test_preserves_function_name_and_args(self):
        @reports_index_errors
        def named(a, b, c=3):
            return a + b + c

        assert named.__name__ == "named"
        assert named(1, 2) == 6
