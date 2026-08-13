"""Tests for agent/tools/search.py."""

from unittest.mock import MagicMock, patch

import pytest

from agent.tools.search import search_dialogue, search_visuals, timecode


class TestTimecode:
    def test_zero(self):
        assert timecode(0.0) == "00:00:00:00"

    def test_whole_seconds(self):
        assert timecode(90.0) == "00:01:30:00"

    def test_rounds_to_nearest_frame(self):
        # 1.0104s * 24fps = 24.25 frames -> rounds to 24 -> rolls into 1s, 0 frames
        assert timecode(1.0104) == "00:00:01:00"

    def test_rounds_down_at_exact_half_frame_boundary(self):
        # Python's round() uses banker's rounding; 0.5 frames at 24fps rounds to even.
        assert timecode(0.5 / 24) == "00:00:00:00"

    def test_hour_rollover(self):
        assert timecode(3600.0) == "01:00:00:00"

    def test_custom_fps(self):
        assert timecode(1.0, fps=30) == "00:00:01:00"

    def test_offset_shifts_to_source_timecode(self):
        # offset_s is the clip's tc_start_s — without it every clip's
        # results would report the same clip-relative range from zero.
        assert timecode(1.0, offset_s=3600.0) == "01:00:01:00"

    def test_zero_offset_is_clip_relative(self):
        assert timecode(1.0, offset_s=0.0) == "00:00:01:00"

    def test_frame_rollover_stays_integer_no_float_artifacts(self):
        # Regression: total_frames must be int, not float, or the %/// below
        # would produce non-integer HH:MM:SS:FF components.
        tc = timecode(59.99)
        assert tc == "00:01:00:00"
        assert all(part.isdigit() for part in tc.split(":"))


@pytest.fixture
def mock_client_and_embed():
    with (
        patch("agent.tools.search.client") as mock_client,
        patch("agent.tools.search.embed_batch") as mock_embed,
    ):
        mock_embed.return_value = [[0.1, 0.2, 0.3]]
        result = MagicMock()
        result.column_names = [
            "clip_id",
            "scene",
            "take",
            "start_s",
            "end_s",
            "reel",
            "tc_start_s",
            "distance",
        ]
        result.result_rows = [["clip_1", "S03", 1, 1.0, 2.0, "A001", 0.0, 0.05]]
        mock_client.return_value.query.return_value = result
        yield mock_client, mock_embed


class TestSearchDialogue:
    def test_returns_rows_with_timecodes(self, mock_client_and_embed):
        mock_client, mock_embed = mock_client_and_embed
        result = MagicMock()
        result.column_names = [
            "clip_id",
            "scene",
            "take",
            "start_s",
            "end_s",
            "speaker",
            "text",
            "delivery",
            "intensity",
            "reel",
            "tc_start_s",
            "distance",
        ]
        result.result_rows = [
            ["clip_1", "S03", 1, 1.0, 2.5, "CELIA", "Hi", "flat", 0.1, "A008", 3600.0, 0.05]
        ]
        mock_client.return_value.query.return_value = result

        rows = search_dialogue("hello")

        assert len(rows) == 1
        assert rows[0]["timecode_in"] == "01:00:01:00"
        assert rows[0]["timecode_out"] == "01:00:02:12"
        assert rows[0]["reel"] == "A008"
        assert "tc_start_s" not in rows[0]
        mock_embed.assert_called_once_with(["hello"])

    def test_scene_and_speaker_filters_build_where_clause(self, mock_client_and_embed):
        mock_client, _ = mock_client_and_embed
        search_dialogue("hello", scene="S12", speaker="Celia")

        sql, kwargs = mock_client.return_value.query.call_args
        assert "scene = %(scene)s" in sql[0]
        assert "speaker ILIKE %(speaker)s" in sql[0]
        assert kwargs["parameters"]["scene"] == "S12"
        assert kwargs["parameters"]["speaker"] == "%Celia%"

    def test_no_filters_means_no_where_clause(self, mock_client_and_embed):
        mock_client, _ = mock_client_and_embed
        search_dialogue("hello")

        sql, _ = mock_client.return_value.query.call_args
        assert "WHERE" not in sql[0]

    def test_clickhouse_failure_returns_error_row_not_raise(self, mock_client_and_embed):
        mock_client, _ = mock_client_and_embed
        mock_client.return_value.query.side_effect = RuntimeError("connection refused")

        rows = search_dialogue("hello")

        assert rows == [
            {
                "error": "The footage index is unreachable (RuntimeError).",
                "error_type": "unreachable",
            }
        ]


class TestSearchVisuals:
    def test_shot_type_filter(self, mock_client_and_embed):
        mock_client, _ = mock_client_and_embed
        search_visuals("a hallway", shot_type="wide")

        sql, kwargs = mock_client.return_value.query.call_args
        assert "shot_type = %(shot_type)s" in sql[0]
        assert kwargs["parameters"]["shot_type"] == "wide"

    def test_failure_is_caught(self, mock_client_and_embed):
        mock_client, _ = mock_client_and_embed
        mock_client.return_value.query.side_effect = ValueError("boom")

        rows = search_visuals("a hallway")

        assert rows == [
            {"error": "The footage index is unreachable (ValueError).", "error_type": "unreachable"}
        ]
