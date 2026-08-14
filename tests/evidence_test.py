"""Tests for agent/tools/_evidence.py."""

from unittest.mock import MagicMock

import pytest

from agent.tools import _evidence


@pytest.fixture(autouse=True)
def _clear_registry():
    """Evidence is a module-level dict keyed by call id; tests must not leak
    into each other."""
    _evidence._by_call_id.clear()
    yield
    _evidence._by_call_id.clear()


class TestRunQuery:
    def test_records_table_row_count_elapsed_and_sql(self):
        client = MagicMock()
        result = MagicMock()
        result.result_rows = [("a",), ("b",)]
        client.query.return_value = result

        out = _evidence.run_query(
            client,
            "call-1",
            "dialogue",
            "SELECT * FROM t WHERE scene = %(scene)s",
            {"scene": "S01"},
        )

        assert out is result
        [evidence] = _evidence.pop("call-1")
        assert evidence["table"] == "dialogue"
        assert evidence["row_count"] == 2
        assert evidence["sql"] == "SELECT * FROM t WHERE scene = 'S01'"
        assert isinstance(evidence["elapsed_ms"], float)
        assert "error" not in evidence

    def test_embedding_vector_param_is_not_rendered_inline(self):
        client = MagicMock()
        result = MagicMock()
        result.result_rows = []
        client.query.return_value = result

        _evidence.run_query(
            client,
            "call-2",
            "dialogue",
            "SELECT cosineDistance(embedding, %(vec)s) FROM t",
            {"vec": [0.1] * 3072},
        )

        [evidence] = _evidence.pop("call-2")
        assert "0.1" not in evidence["sql"]
        assert "<embedding vector, 3072 dims>" in evidence["sql"]

    def test_no_call_id_records_nothing(self):
        client = MagicMock()
        result = MagicMock()
        result.result_rows = []
        client.query.return_value = result

        _evidence.run_query(client, None, "dialogue", "SELECT 1", {})

        assert _evidence.pop(None) == []
        assert _evidence._by_call_id == {}

    def test_failing_query_still_records_evidence_with_the_error_and_reraises(self):
        client = MagicMock()
        client.query.side_effect = RuntimeError("connection refused")

        with pytest.raises(RuntimeError, match="connection refused"):
            _evidence.run_query(client, "call-3", "dialogue", "SELECT 1", {})

        [evidence] = _evidence.pop("call-3")
        assert evidence["table"] == "dialogue"
        assert evidence["error"] == "connection refused"
        assert "row_count" not in evidence
        assert isinstance(evidence["elapsed_ms"], float)

    def test_two_queries_same_call_id_both_recorded_in_order(self):
        client = MagicMock()
        result = MagicMock()
        result.result_rows = [("a",)]
        client.query.return_value = result

        _evidence.run_query(client, "call-4", "clips", "SELECT 1", {})
        _evidence.run_query(client, "call-4", "visuals", "SELECT 2", {})

        evidence = _evidence.pop("call-4")
        assert [e["table"] for e in evidence] == ["clips", "visuals"]


class TestPop:
    def test_pop_clears_the_entry(self):
        client = MagicMock()
        result = MagicMock()
        result.result_rows = []
        client.query.return_value = result
        _evidence.run_query(client, "call-5", "clips", "SELECT 1", {})

        assert len(_evidence.pop("call-5")) == 1
        assert _evidence.pop("call-5") == []

    def test_pop_unknown_call_id_returns_empty(self):
        assert _evidence.pop("never-recorded") == []
