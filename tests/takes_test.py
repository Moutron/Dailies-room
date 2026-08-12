"""Tests for agent/tools/takes.py."""

from unittest.mock import MagicMock, patch

import pytest

from agent.tools.takes import compare_takes

CLIP_COLUMNS = [
    "clip_id",
    "scene",
    "slate",
    "take",
    "dominant_mood",
    "technical_notes",
    "characters_present",
    "summary",
]


def _clip_result_row(clip_id, slate, take, mood="neutral"):
    return [clip_id, "S03", slate, take, mood, [], ["CELIA"], "summary"]


def _mk_result(column_names, rows):
    result = MagicMock()
    result.column_names = column_names
    result.result_rows = rows
    return result


@pytest.fixture
def mock_client():
    with (
        patch("agent.tools.takes.client") as mock_client,
        patch("agent.tools.takes.embed_batch") as mock_embed,
    ):
        mock_embed.return_value = [[0.1, 0.2]]
        yield mock_client, mock_embed


class TestCompareTakes:
    def test_without_query_returns_all_dialogue_for_each_take(self, mock_client):
        client, _ = mock_client
        clips = _mk_result(CLIP_COLUMNS, [_clip_result_row("c1", "2A", 1)])
        dialogue = _mk_result(
            ["start_s", "end_s", "speaker", "text", "delivery", "intensity"],
            [[1.0, 2.0, "CELIA", "Hi", "flat", 0.1]],
        )
        span = _mk_result([], [])
        span.result_rows = [(1.0, 2.0)]

        client.return_value.query.side_effect = [clips, dialogue, span]

        rows = compare_takes(scene="S03")

        assert len(rows) == 1
        assert rows[0]["dialogue"][0]["text"] == "Hi"
        assert rows[0]["dialogue"][0]["timecode_in"] == "00:00:01:00"
        assert rows[0]["timecode_in"] == "00:00:01:00"
        assert rows[0]["timecode_out"] == "00:00:02:00"

    def test_with_query_drops_takes_without_matching_line(self, mock_client):
        client, embed = mock_client
        clips = _mk_result(
            CLIP_COLUMNS,
            [_clip_result_row("c1", "2A", 1), _clip_result_row("c2", "2A", 2)],
        )
        matching_dialogue = _mk_result(
            ["start_s", "end_s", "speaker", "text", "delivery", "intensity", "distance"],
            [[1.0, 2.0, "CELIA", "Hi", "angry", 0.9, 0.1]],
        )
        no_dialogue = _mk_result(
            ["start_s", "end_s", "speaker", "text", "delivery", "intensity", "distance"],
            [],
        )
        span = _mk_result([], [])
        span.result_rows = [(1.0, 2.0)]

        client.return_value.query.side_effect = [clips, matching_dialogue, span, no_dialogue]

        rows = compare_takes(scene="S03", query="the line about the hand")

        assert len(rows) == 1
        assert rows[0]["clip_id"] == "c1"
        embed.assert_called_once_with(["the line about the hand"])

    def test_slate_filter_adds_where_clause(self, mock_client):
        client, _ = mock_client
        clips = _mk_result(CLIP_COLUMNS, [])
        client.return_value.query.return_value = clips

        compare_takes(scene="S03", slate="2A")

        sql, kwargs = client.return_value.query.call_args
        assert "c.slate = %(slate)s" in sql[0]
        assert kwargs["parameters"]["slate"] == "2A"

    def test_clickhouse_failure_returns_error_row(self, mock_client):
        client, _ = mock_client
        client.return_value.query.side_effect = RuntimeError("down")

        rows = compare_takes(scene="S03")

        assert rows == [{"error": "The footage index is unreachable (RuntimeError)."}]
