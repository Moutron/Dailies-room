"""Tests for ui/server/clip_meta.py."""

from unittest.mock import MagicMock, patch

from ui.server.clip_meta import clip_dialogue, clip_meta, index_stats

META_COLUMNS = [
    "clip_id",
    "scene",
    "slate",
    "take",
    "location",
    "day_night",
    "duration_s",
    "reel",
    "ingested_at",
    "tc_start_s",
    "shot_type",
    "camera_movement",
    "description",
    "notable_elements",
    "dialogue_count",
    "circled",
]


@patch("ui.server.clip_meta.client")
class TestClipMeta:
    def test_returns_none_when_the_clip_is_not_indexed(self, mock_client):
        result = MagicMock()
        result.result_rows = []
        mock_client.return_value.query.return_value = result

        assert clip_meta("does_not_exist") is None

    def test_returns_the_joined_row_as_a_dict(self, mock_client):
        result = MagicMock()
        result.column_names = META_COLUMNS
        result.result_rows = [
            [
                "01_1a_take",
                "S01",
                "1A",
                1,
                "Amsterdam canal bridge",
                "DAY",
                5.5,
                "A002",
                "2026-08-12T21:47:00",
                21600.0,
                "medium",
                "static",
                "Two people talk on a bridge.",
                ["bridge", "canal"],
                2,
                0,
            ]
        ]
        mock_client.return_value.query.return_value = result

        meta = clip_meta("01_1a_take")

        assert meta["clip_id"] == "01_1a_take"
        assert meta["duration_s"] == 5.5
        assert meta["shot_type"] == "medium"
        assert meta["notable_elements"] == ["bridge", "canal"]
        assert meta["dialogue_count"] == 2
        assert meta["ingested_at"] == "2026-08-12T21:47:00"
        assert meta["circled"] is False

    def test_circled_field_is_a_real_bool_not_the_raw_uint8(self, mock_client):
        result = MagicMock()
        result.column_names = META_COLUMNS
        result.result_rows = [
            [
                "01_1a_take",
                "S01",
                "1A",
                1,
                "Amsterdam canal bridge",
                "DAY",
                5.5,
                "A002",
                "2026-08-12T21:47:00",
                21600.0,
                "medium",
                "static",
                "Two people talk on a bridge.",
                ["bridge", "canal"],
                2,
                1,
            ]
        ]
        mock_client.return_value.query.return_value = result

        meta = clip_meta("01_1a_take")

        assert meta["circled"] is True

    def test_queries_by_clip_id_parameter(self, mock_client):
        result = MagicMock()
        result.result_rows = []
        mock_client.return_value.query.return_value = result

        clip_meta("01_1a_take")

        _, kwargs = mock_client.return_value.query.call_args
        assert kwargs["parameters"] == {"clip_id": "01_1a_take"}


@patch("ui.server.clip_meta.client")
class TestClipDialogue:
    def test_returns_none_when_the_clip_is_not_indexed(self, mock_client):
        exists_result = MagicMock()
        exists_result.result_rows = [(0,)]
        mock_client.return_value.query.return_value = exists_result

        assert clip_dialogue("does_not_exist") is None

    def test_returns_dialogue_rows_ordered_by_start_s(self, mock_client):
        exists_result = MagicMock()
        exists_result.result_rows = [(1,)]
        dialogue_result = MagicMock()
        dialogue_result.column_names = [
            "segment_idx",
            "start_s",
            "end_s",
            "speaker",
            "text",
            "delivery",
        ]
        dialogue_result.result_rows = [
            [0, 0.0, 3.8, "ROBOT_ARM_WOMAN", "Why don't you just admit it?", "accusatory"],
            [1, 4.0, 4.9, "MAN", "I'm not freaked out by, but it's...", "defensive"],
        ]
        mock_client.return_value.query.side_effect = [exists_result, dialogue_result]

        lines = clip_dialogue("01_1b_take")

        assert len(lines) == 2
        assert lines[0]["speaker"] == "ROBOT_ARM_WOMAN"
        assert lines[1]["end_s"] == 4.9

    def test_indexed_clip_with_zero_dialogue_lines_returns_empty_list_not_none(self, mock_client):
        exists_result = MagicMock()
        exists_result.result_rows = [(1,)]
        dialogue_result = MagicMock()
        dialogue_result.column_names = [
            "segment_idx",
            "start_s",
            "end_s",
            "speaker",
            "text",
            "delivery",
        ]
        dialogue_result.result_rows = []
        mock_client.return_value.query.side_effect = [exists_result, dialogue_result]

        lines = clip_dialogue("03_2a_take")

        assert lines == []

    def test_queries_by_clip_id_parameter(self, mock_client):
        exists_result = MagicMock()
        exists_result.result_rows = [(1,)]
        dialogue_result = MagicMock()
        dialogue_result.column_names = [
            "segment_idx",
            "start_s",
            "end_s",
            "speaker",
            "text",
            "delivery",
        ]
        dialogue_result.result_rows = []
        mock_client.return_value.query.side_effect = [exists_result, dialogue_result]

        clip_dialogue("01_1a_take")

        _, kwargs = mock_client.return_value.query.call_args
        assert kwargs["parameters"] == {"clip_id": "01_1a_take"}


@patch("ui.server.clip_meta.client")
class TestIndexStats:
    def test_returns_real_count_and_total_duration(self, mock_client):
        result = MagicMock()
        result.result_rows = [(6, 29.83)]
        mock_client.return_value.query.return_value = result

        assert index_stats() == {"clip_count": 6, "total_duration_s": 29.83}

    def test_null_sum_on_an_empty_index_becomes_zero(self, mock_client):
        result = MagicMock()
        result.result_rows = [(0, None)]
        mock_client.return_value.query.return_value = result

        assert index_stats() == {"clip_count": 0, "total_duration_s": 0.0}
