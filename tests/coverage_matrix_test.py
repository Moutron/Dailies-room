"""Tests for ui/server/coverage_matrix.py."""

from unittest.mock import MagicMock, patch

from ui.server.coverage_matrix import coverage_matrix

COLUMNS = [
    "clip_id",
    "scene",
    "slate",
    "take",
    "location",
    "day_night",
    "characters_present",
    "shot_type",
    "dialogue_count",
]

# The real six-clip index (DESIGN_IMPLEMENTATION_PLAN.md's "What actually
# landed" for Prompt 5): S01/1A has three clips (all medium, no tight
# coverage); S03 has three separate slates, one of which (2C) is
# medium_close, i.e. tight.
REAL_INDEX_ROWS = [
    ["01_1a_take", "S01", "1A", 1, "Amsterdam canal bridge", "DAY", ["Thom", "Celia"], "medium", 1],
    ["01_1b_take", "S01", "1A", 1, "Amsterdam canal bridge", "DAY", ["Thom", "Celia"], "medium", 2],
    ["01_1c_take", "S01", "1A", 1, "Amsterdam canal bridge", "DAY", ["Thom", "Celia"], "medium", 1],
    ["03_2a_take", "S03", "2A", 1, "Rooftop lookout, Amsterdam", "NIGHT", ["Bruno"], "wide", 0],
    [
        "03_2c_take",
        "S03",
        "2C",
        3,
        "Rooftop lookout, Amsterdam",
        "NIGHT",
        ["Bruno"],
        "medium_close",
        0,
    ],
    ["03_2e_take", "S03", "2E", 5, "Rooftop lookout, Amsterdam", "NIGHT", ["Bruno"], "wide", 0],
]


def _result(rows):
    result = MagicMock()
    result.column_names = COLUMNS
    result.result_rows = rows
    return result


@patch("ui.server.coverage_matrix.client")
class TestCoverageMatrix:
    def test_maps_shot_types_into_the_five_display_columns(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        matrix = coverage_matrix()

        assert matrix["columns"] == ["WIDE", "MED", "MCU", "CU", "INSERT"]
        rows_by_slate = {(r["scene"], r["slate"]): r for r in matrix["rows"]}

        s01 = rows_by_slate[("S01", "1A")]
        assert sorted(s01["cells"]["MED"]) == ["01_1a_take", "01_1b_take", "01_1c_take"]
        assert s01["cells"]["WIDE"] == []
        assert s01["cells"]["MCU"] == []
        assert s01["cells"]["CU"] == []
        assert s01["cells"]["INSERT"] == []

        s03_2c = rows_by_slate[("S03", "2C")]
        assert s03_2c["cells"]["MCU"] == ["03_2c_take"]

        s03_2a = rows_by_slate[("S03", "2A")]
        assert s03_2a["cells"]["WIDE"] == ["03_2a_take"]

    def test_row_without_a_tight_shot_type_is_flagged(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        matrix = coverage_matrix()
        rows_by_slate = {(r["scene"], r["slate"]): r for r in matrix["rows"]}

        assert rows_by_slate[("S01", "1A")]["status"] == "NO TIGHT COVERAGE"
        assert rows_by_slate[("S01", "1A")]["has_tight_coverage"] is False
        assert rows_by_slate[("S03", "2A")]["status"] == "NO TIGHT COVERAGE"

    def test_row_with_a_medium_close_shot_is_complete(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        matrix = coverage_matrix()
        rows_by_slate = {(r["scene"], r["slate"]): r for r in matrix["rows"]}

        assert rows_by_slate[("S03", "2C")]["status"] == "COMPLETE"
        assert rows_by_slate[("S03", "2C")]["has_tight_coverage"] is True

    def test_classification_maps_med_only_to_coverage_gap(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        matrix = coverage_matrix()
        rows_by_slate = {(r["scene"], r["slate"]): r for r in matrix["rows"]}

        assert rows_by_slate[("S01", "1A")]["classification"] == "coverage gap"

    def test_classification_maps_wide_only_to_wide_coverage_only(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        matrix = coverage_matrix()
        rows_by_slate = {(r["scene"], r["slate"]): r for r in matrix["rows"]}

        assert rows_by_slate[("S03", "2A")]["classification"] == "wide coverage only"
        assert rows_by_slate[("S03", "2E")]["classification"] == "wide coverage only"

    def test_a_complete_row_has_no_classification(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        matrix = coverage_matrix()
        rows_by_slate = {(r["scene"], r["slate"]): r for r in matrix["rows"]}

        assert rows_by_slate[("S03", "2C")]["classification"] is None

    def test_classification_maps_no_visuals_data_to_never_appeared(self, mock_client):
        rows = [
            ["04_never", "S04", "9Z", 1, "Nowhere", "DAY", [], None, 0],
        ]
        mock_client.return_value.query.return_value = _result(rows)

        matrix = coverage_matrix()

        assert matrix["rows"][0]["classification"] == "never appeared"

    def test_scene_level_gap_is_s01_only_since_s03_has_2c(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        matrix = coverage_matrix()

        assert matrix["gap_scenes"] == ["S01"]
        assert matrix["headline"] == "Scene S01 is missing tight coverage."

    def test_stats_are_real_counts(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        matrix = coverage_matrix()

        assert matrix["stats"]["takes_printed"] == 6
        assert matrix["stats"]["scenes"] == 2
        # 3 non-tight rows: S01/1A, S03/2A, S03/2E.
        assert matrix["stats"]["gaps_flagged"] == 3

    def test_description_notes_no_dialogue_when_every_clip_in_the_row_has_none(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        matrix = coverage_matrix()
        rows_by_slate = {(r["scene"], r["slate"]): r for r in matrix["rows"]}

        assert "no dialogue" in rows_by_slate[("S03", "2A")]["description"]
        assert "no dialogue" not in rows_by_slate[("S01", "1A")]["description"]

    def test_unknown_shot_type_is_not_dropped(self, mock_client):
        rows = [*REAL_INDEX_ROWS, ["99_extra", "S99", "9A", 1, "Nowhere", "DAY", [], "unknown", 0]]
        mock_client.return_value.query.return_value = _result(rows)

        matrix = coverage_matrix()
        rows_by_slate = {(r["scene"], r["slate"]): r for r in matrix["rows"]}

        s99 = rows_by_slate[("S99", "9A")]
        assert s99["unknown_clip_ids"] == ["99_extra"]
        assert all(s99["cells"][c] == [] for c in matrix["columns"])

    def test_returns_the_rendered_sql(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        matrix = coverage_matrix()

        assert "clips" in matrix["sql"]
        assert "visuals" in matrix["sql"]
