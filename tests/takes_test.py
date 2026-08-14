"""Tests for agent/tools/takes.py."""

from unittest.mock import MagicMock, patch

import pytest

from agent.tools.takes import compare_takes

RESULT_COLUMNS = [
    "clip_id",
    "scene",
    "slate",
    "take",
    "dominant_mood",
    "technical_notes",
    "characters_present",
    "summary",
    "duration_s",
    "reel",
    "tc_start_s",
    "dialogue_lines",
    "vis_start_s",
    "vis_end_s",
]


def _clip_row(
    clip_id,
    slate,
    take,
    dialogue_lines,
    vis_start_s=1.0,
    vis_end_s=2.0,
    mood="neutral",
    reel="A001",
    tc_start_s=0.0,
    duration_s=5.0,
):
    return [
        clip_id,
        "S03",
        slate,
        take,
        mood,
        [],
        ["CELIA"],
        "summary",
        duration_s,
        reel,
        tc_start_s,
        dialogue_lines,
        vis_start_s,
        vis_end_s,
    ]


def _mk_result(rows, columns=RESULT_COLUMNS):
    result = MagicMock()
    result.column_names = columns
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
        dialogue_lines = [(1.0, 2.0, "CELIA", "Hi", "flat", 0.1)]
        client.return_value.query.return_value = _mk_result(
            [_clip_row("c1", "2A", 1, dialogue_lines)]
        )

        rows = compare_takes(scene="S03")

        assert len(rows) == 1
        assert rows[0]["dialogue"][0]["text"] == "Hi"
        assert rows[0]["dialogue"][0]["timecode_in"] == "00:00:01:00"
        assert rows[0]["timecode_in"] == "00:00:01:00"
        assert rows[0]["timecode_out"] == "00:00:02:00"
        assert rows[0]["reel"] == "A001"
        assert "tc_start_s" not in rows[0]
        # Single round trip for the whole comparison, not one query per take.
        assert client.return_value.query.call_count == 1

    def test_source_timecode_offsets_dialogue_and_span(self, mock_client):
        # Two clips with the exact same clip-relative dialogue/visual range
        # but different tc_start_s must report different timecodes — this
        # is the bug where every result read 00:00:00:00-00:00:05:00.
        client, _ = mock_client
        dialogue_lines = [(1.0, 2.0, "CELIA", "Hi", "flat", 0.1)]
        client.return_value.query.return_value = _mk_result(
            [_clip_row("c1", "2A", 1, dialogue_lines, reel="A008", tc_start_s=3600.0)]
        )

        rows = compare_takes(scene="S03")

        assert rows[0]["reel"] == "A008"
        assert rows[0]["dialogue"][0]["timecode_in"] == "01:00:01:00"
        assert rows[0]["timecode_in"] == "01:00:01:00"
        assert rows[0]["timecode_out"] == "01:00:02:00"

    def test_with_query_only_returns_takes_with_matching_line(self, mock_client):
        # The dialogue join is an INNER JOIN when `query` is given, so a take
        # with no line under the distance threshold never appears in the
        # result at all — there's nothing to "drop" in Python anymore.
        client, embed = mock_client
        dialogue_lines = [(1.0, 2.0, "CELIA", "Hi", "angry", 0.9, 0.1)]
        client.return_value.query.return_value = _mk_result(
            [_clip_row("c1", "2A", 1, dialogue_lines)]
        )

        rows = compare_takes(scene="S03", query="the line about the hand")

        assert len(rows) == 1
        assert rows[0]["clip_id"] == "c1"
        embed.assert_called_once_with(["the line about the hand"])

    def test_slate_filter_adds_where_clause(self, mock_client):
        client, _ = mock_client
        client.return_value.query.return_value = _mk_result([])

        compare_takes(scene="S03", slate="2A")

        sql, kwargs = client.return_value.query.call_args
        assert "c.slate = %(slate)s" in sql[0]
        assert kwargs["parameters"]["slate"] == "2A"

    def test_clickhouse_failure_returns_error_row(self, mock_client):
        client, _ = mock_client
        client.return_value.query.side_effect = RuntimeError("down")

        rows = compare_takes(scene="S03")

        assert rows == [
            {
                "error": "The footage index is unreachable (RuntimeError).",
                "error_type": "unreachable",
            }
        ]
