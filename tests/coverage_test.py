"""Tests for agent/tools/coverage.py."""

from unittest.mock import MagicMock, patch

import pytest

from agent.tools.coverage import get_coverage

COLUMNS = [
    "clip_id",
    "scene",
    "slate",
    "take",
    "location",
    "day_night",
    "summary",
    "characters_present",
    "characters_expected",
    "technical_notes",
    "shot_type",
    "camera_movement",
    "characters_visible",
    "start_s",
    "end_s",
]


def _row(
    clip_id,
    slate,
    take,
    shot_type,
    characters_visible,
    characters_present=None,
    characters_expected=None,
):
    return [
        clip_id,
        "S03",
        slate,
        take,
        "Bridge",
        "day",
        "summary",
        characters_present or characters_visible,
        characters_expected or ["CELIA", "THOM", "MARCO"],
        [],
        shot_type,
        "static",
        characters_visible,
        0.0,
        5.0,
    ]


@pytest.fixture
def mock_client():
    with patch("agent.tools.coverage.client") as mock_client:
        yield mock_client


class TestGetCoverage:
    def test_no_scene_lists_every_scene_without_gap_fields(self, mock_client):
        result = MagicMock()
        result.column_names = COLUMNS
        result.result_rows = [_row("c1", "2A", 1, "wide", ["CELIA"])]
        mock_client.return_value.query.return_value = result

        rows = get_coverage()

        assert len(rows) == 1
        assert "never_appeared" not in rows[0]
        assert rows[0]["timecode_in"] == "00:00:00:00"
        assert "characters_visible" not in rows[0]

    def test_scene_computes_never_appeared(self, mock_client):
        result = MagicMock()
        result.column_names = COLUMNS
        result.result_rows = [
            _row(
                "c1",
                "2A",
                1,
                "wide",
                ["CELIA"],
                characters_present=["CELIA"],
                characters_expected=["CELIA", "THOM"],
            ),
        ]
        mock_client.return_value.query.return_value = result

        rows = get_coverage(scene="S03")

        assert rows[0]["never_appeared"] == ["THOM"]

    def test_scene_computes_no_tight_shot(self, mock_client):
        # CELIA appears, but only ever in a wide shot -> never in a tight shot.
        result = MagicMock()
        result.column_names = COLUMNS
        result.result_rows = [
            _row(
                "c1",
                "2A",
                1,
                "wide",
                ["CELIA"],
                characters_present=["CELIA"],
                characters_expected=["CELIA"],
            ),
        ]
        mock_client.return_value.query.return_value = result

        rows = get_coverage(scene="S03")

        assert rows[0]["no_tight_shot"] == ["CELIA"]
        assert rows[0]["wide_coverage"] == ["CELIA"]

    def test_scene_tight_shot_excludes_character_from_gaps(self, mock_client):
        result = MagicMock()
        result.column_names = COLUMNS
        result.result_rows = [
            _row(
                "c1",
                "2A",
                1,
                "close-up",
                ["CELIA"],
                characters_present=["CELIA"],
                characters_expected=["CELIA"],
            ),
        ]
        mock_client.return_value.query.return_value = result

        rows = get_coverage(scene="S03")

        assert rows[0]["no_tight_shot"] == []
        assert rows[0]["wide_coverage"] == []

    def test_scene_with_no_rows_skips_gap_computation(self, mock_client):
        result = MagicMock()
        result.column_names = COLUMNS
        result.result_rows = []
        mock_client.return_value.query.return_value = result

        rows = get_coverage(scene="S99")

        assert rows == []

    def test_clickhouse_failure_returns_error_row(self, mock_client):
        mock_client.return_value.query.side_effect = RuntimeError("down")

        rows = get_coverage(scene="S03")

        assert rows == [{"error": "The footage index is unreachable (RuntimeError)."}]
