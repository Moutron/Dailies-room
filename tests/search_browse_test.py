"""Tests for ui/server/search.py — Screen #1d's search bar."""

from unittest.mock import MagicMock, patch

from ui.server.search import browse_search


class TestSemanticSearch:
    def test_lower_distance_produces_a_higher_score(self):
        dialogue_rows = [
            {
                "clip_id": "01_1b_take",
                "scene": "S01",
                "take": 1,
                "reel": "A002",
                "timecode_in": "01:00:11:12",
                "speaker": "CELIA",
                "text": "my robot hand",
                "delivery": "defensive",
                "distance": 0.09,
            }
        ]
        with (
            patch("ui.server.search.search_dialogue", return_value=dialogue_rows),
            patch("ui.server.search.search_visuals", return_value=[]),
        ):
            result = browse_search("robotic hand", "semantic")

        assert result["mode"] == "semantic"
        assert len(result["hits"]) == 1
        hit = result["hits"][0]
        assert hit["kind"] == "dialogue"
        assert hit["score"] == 0.91
        assert hit["quote"] == "my robot hand"
        assert hit["note_label"] == "performance note"

    def test_results_are_ranked_best_score_first(self):
        dialogue_rows = [
            {
                "clip_id": "close_match",
                "scene": "S01",
                "take": 1,
                "reel": "A002",
                "timecode_in": "00:00:00:00",
                "speaker": "CELIA",
                "text": "close match line",
                "delivery": "flat",
                "distance": 0.05,
            }
        ]
        visual_rows = [
            {
                "clip_id": "far_match",
                "scene": "S03",
                "take": 1,
                "reel": "A007",
                "timecode_in": "00:00:00:00",
                "description": "distant visual match",
                "camera_movement": "static",
                "distance": 0.6,
            }
        ]
        with (
            patch("ui.server.search.search_dialogue", return_value=dialogue_rows),
            patch("ui.server.search.search_visuals", return_value=visual_rows),
        ):
            result = browse_search("robotic hand", "semantic")

        assert [h["clip_id"] for h in result["hits"]] == ["close_match", "far_match"]
        assert result["hits"][0]["score"] > result["hits"][1]["score"]

    def test_error_rows_from_a_dead_index_are_dropped_not_crashed_on(self):
        error_rows = [
            {
                "error": "The footage index is unreachable (RuntimeError).",
                "error_type": "unreachable",
            }
        ]
        with (
            patch("ui.server.search.search_dialogue", return_value=error_rows),
            patch("ui.server.search.search_visuals", return_value=error_rows),
        ):
            result = browse_search("robotic hand", "semantic")

        assert result["hits"] == []

    def test_visual_hits_carry_no_speaker_and_a_camera_movement_note(self):
        visual_rows = [
            {
                "clip_id": "03_2c_take",
                "scene": "S03",
                "take": 3,
                "reel": "A007",
                "timecode_in": "00:00:00:00",
                "description": "a sniper aiming a rifle",
                "camera_movement": "static",
                "distance": 0.2,
            }
        ]
        with (
            patch("ui.server.search.search_dialogue", return_value=[]),
            patch("ui.server.search.search_visuals", return_value=visual_rows),
        ):
            result = browse_search("rifle", "semantic")

        hit = result["hits"][0]
        assert hit["kind"] == "visual"
        assert hit["speaker"] is None
        assert hit["note"] == "static"
        assert hit["note_label"] == "camera movement"


class TestKeywordSearch:
    def _result(self, columns, rows):
        result = MagicMock()
        result.column_names = columns
        result.result_rows = rows
        return result

    def test_keyword_hits_never_carry_a_score(self):
        dialogue_result = self._result(
            [
                "clip_id",
                "scene",
                "take",
                "start_s",
                "speaker",
                "text",
                "delivery",
                "reel",
                "tc_start_s",
            ],
            [["01_1b_take", "S01", 1, 5.5, "CELIA", "my robot hand", "defensive", "A002", 3611.5]],
        )
        empty_visuals = self._result(
            [
                "clip_id",
                "scene",
                "take",
                "start_s",
                "description",
                "camera_movement",
                "reel",
                "tc_start_s",
            ],
            [],
        )
        with patch("ui.server.search.client") as mock_client:
            mock_client.return_value.query.side_effect = [dialogue_result, empty_visuals]
            result = browse_search("robot", "keyword")

        assert result["mode"] == "keyword"
        assert len(result["hits"]) == 1
        assert result["hits"][0]["score"] is None
        assert result["hits"][0]["quote"] == "my robot hand"
        # Regression: an earlier version of the dialogue keyword SQL didn't
        # select `delivery`, so every keyword dialogue hit's performance
        # note silently rendered as null even though real data exists.
        assert result["hits"][0]["note"] == "defensive"

    def test_keyword_search_uses_ilike_over_both_tables(self):
        empty = self._result(["clip_id"], [])
        with patch("ui.server.search.client") as mock_client:
            mock_client.return_value.query.side_effect = [empty, empty]
            browse_search("robot", "keyword")

        calls = mock_client.return_value.query.call_args_list
        assert len(calls) == 2
        first_sql = calls[0].args[0]
        second_sql = calls[1].args[0]
        assert "dialogue" in first_sql and "text ILIKE" in first_sql
        assert "visuals" in second_sql and "description ILIKE" in second_sql
        assert calls[0].kwargs["parameters"]["pattern"] == "%robot%"

    def test_empty_query_string_is_handled_by_the_route_not_here(self):
        empty = self._result(
            [
                "clip_id",
                "scene",
                "take",
                "start_s",
                "speaker",
                "text",
                "delivery",
                "reel",
                "tc_start_s",
            ],
            [],
        )
        with patch("ui.server.search.client") as mock_client:
            mock_client.return_value.query.side_effect = [empty, empty]
            result = browse_search("", "keyword")

        assert result["hits"] == []
