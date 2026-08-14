"""Tests for ui/server/shot_list.py.

Rows are generated live from coverage_matrix()'s real per-row
classification -- never a fixture read straight into the table -- so these
tests mock coverage_matrix() (the aggregate) rather than the raw ClickHouse
rows underneath it; ui/server/coverage_matrix_test.py already covers that
mapping itself.
"""

from unittest.mock import MagicMock, patch

from ui.server.shot_list import generate_rows, list_rows, set_selected

# The real coverage_matrix() shape: S01/1A is a
# coverage gap (MED only), S03/2A and S03/2E are wide-coverage-only, S03/2C
# is complete (no classification).
MATRIX_ROWS = [
    {
        "scene": "S01",
        "slate": "1A",
        "take": 1,
        "location": "Amsterdam canal bridge",
        "day_night": "DAY",
        "description": "Amsterdam canal bridge, Day — 2 chars",
        "cells": {
            "WIDE": [],
            "MED": ["01_1a_take", "01_1b_take", "01_1c_take"],
            "MCU": [],
            "CU": [],
            "INSERT": [],
        },
        "unknown_clip_ids": [],
        "no_visuals_clip_ids": [],
        "has_tight_coverage": False,
        "status": "NO TIGHT COVERAGE",
        "classification": "coverage gap",
    },
    {
        "scene": "S03",
        "slate": "2A",
        "take": 1,
        "location": "Rooftop lookout, Amsterdam",
        "day_night": "NIGHT",
        "description": "Rooftop lookout, Amsterdam, Night — 1 char — no dialogue",
        "cells": {"WIDE": ["03_2a_take"], "MED": [], "MCU": [], "CU": [], "INSERT": []},
        "unknown_clip_ids": [],
        "no_visuals_clip_ids": [],
        "has_tight_coverage": False,
        "status": "NO TIGHT COVERAGE",
        "classification": "wide coverage only",
    },
    {
        "scene": "S03",
        "slate": "2C",
        "take": 3,
        "location": "Rooftop lookout, Amsterdam",
        "day_night": "NIGHT",
        "description": "Rooftop lookout, Amsterdam, Night — 1 char — no dialogue",
        "cells": {"WIDE": [], "MED": [], "MCU": ["03_2c_take"], "CU": [], "INSERT": []},
        "unknown_clip_ids": [],
        "no_visuals_clip_ids": [],
        "has_tight_coverage": True,
        "status": "COMPLETE",
        "classification": None,
    },
]

MATRIX = {
    "columns": ["WIDE", "MED", "MCU", "CU", "INSERT"],
    "rows": MATRIX_ROWS,
    "stats": {"takes_printed": 5, "scenes": 2, "gaps_flagged": 2},
    "gap_scenes": ["S01"],
    "headline": "Scene S01 is missing tight coverage.",
    "sql": "SELECT ...",
}


def _selected_result(rows):
    result = MagicMock()
    result.result_rows = rows
    return result


class TestGenerateRows:
    @patch("ui.server.shot_list.coverage_matrix", return_value=MATRIX)
    def test_only_flagged_rows_are_generated(self, mock_matrix):
        rows = generate_rows()

        assert {r["row_id"] for r in rows} == {"S01-1A", "S03-2A"}

    @patch("ui.server.shot_list.coverage_matrix", return_value=MATRIX)
    def test_row_id_is_deterministic_from_scene_and_slate(self, mock_matrix):
        rows = generate_rows()

        s01 = next(r for r in rows if r["row_id"] == "S01-1A")
        assert s01["title"] == "S01 · 1A"
        assert s01["classification"] == "coverage gap"
        assert s01["source_clip"] == "01_1a_take"

    @patch("ui.server.shot_list.coverage_matrix", return_value=MATRIX)
    def test_reason_names_the_real_shot_size_and_take_count(self, mock_matrix):
        rows = generate_rows()

        s01 = next(r for r in rows if r["row_id"] == "S01-1A")
        assert "MED" in s01["reason"]
        assert "3 takes" in s01["reason"]

    @patch("ui.server.shot_list.coverage_matrix", return_value=MATRIX)
    def test_wide_coverage_only_gets_its_own_reason_text(self, mock_matrix):
        rows = generate_rows()

        s03 = next(r for r in rows if r["row_id"] == "S03-2A")
        assert "wide" in s03["reason"].lower()
        assert s03["source_clip"] == "03_2a_take"

    @patch("ui.server.shot_list.coverage_matrix", return_value=MATRIX)
    def test_qualifier_is_real_location_and_day_night(self, mock_matrix):
        rows = generate_rows()

        s01 = next(r for r in rows if r["row_id"] == "S01-1A")
        assert s01["qualifier"] == "amsterdam canal bridge, day"


@patch("ui.server.shot_list.client")
@patch("ui.server.shot_list.coverage_matrix", return_value=MATRIX)
class TestListRows:
    def test_upserts_generated_rows_and_returns_them(self, mock_matrix, mock_client):
        mock_client.return_value.query.return_value = _selected_result([])

        rows = list_rows()

        assert {r["row_id"] for r in rows} == {"S01-1A", "S03-2A"}
        assert all(r["selected"] is False for r in rows)
        mock_client.return_value.insert.assert_called_once()
        call_args = mock_client.return_value.insert.call_args
        assert call_args[0][0] == "shot_list"
        assert call_args[1]["column_names"] == [
            "row_id",
            "title",
            "reason",
            "source_clip",
            "classification",
            "selected",
            "created_at",
        ]

    def test_preserves_a_previously_selected_row(self, mock_matrix, mock_client):
        mock_client.return_value.query.return_value = _selected_result([("S01-1A", 1)])

        rows = list_rows()

        by_id = {r["row_id"]: r for r in rows}
        assert by_id["S01-1A"]["selected"] is True
        assert by_id["S03-2A"]["selected"] is False


@patch("ui.server.shot_list.client")
@patch("ui.server.shot_list.coverage_matrix", return_value=MATRIX)
class TestSetSelected:
    def test_returns_none_for_a_row_that_is_not_currently_flagged(self, mock_matrix, mock_client):
        result = set_selected("does-not-exist", True)

        assert result is None
        mock_client.return_value.insert.assert_not_called()

    def test_writes_a_new_row_with_the_toggled_selection(self, mock_matrix, mock_client):
        result = set_selected("S01-1A", True)

        assert result["row_id"] == "S01-1A"
        assert result["selected"] is True
        mock_client.return_value.insert.assert_called_once()
        inserted_row = mock_client.return_value.insert.call_args[0][1][0]
        assert inserted_row[0] == "S01-1A"
        assert inserted_row[-2] == 1

    def test_created_at_is_written_explicitly_never_left_to_the_column_default(
        self, mock_matrix, mock_client
    ):
        # Same real dedup bug and fix as circle.py's updated_at -- see that
        # module's docstring and tests/circle_test.py.
        set_selected("S01-1A", True)
        first = mock_client.return_value.insert.call_args[0][1][0][-1]
        mock_client.return_value.insert.reset_mock()
        set_selected("S01-1A", True)
        second = mock_client.return_value.insert.call_args[0][1][0][-1]

        assert first != second
