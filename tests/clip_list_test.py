"""Tests for ui/server/clip_list.py."""

from unittest.mock import MagicMock, patch

from ui.server.clip_list import clip_list

COLUMNS = ["clip_id", "reel", "scene", "slate", "take", "duration_s", "shot_type", "circled"]

# The real six-clip index (DESIGN_IMPLEMENTATION_PLAN.md's Prompt 5/6 notes):
# all three S01 clips share scene=S01/slate=1A/take=1 -- different
# performances of the same setup, not different takes.
REAL_INDEX_ROWS = [
    ["01_1a_take", "A002", "S01", "1A", 1, 4.8, "medium", 1],
    ["01_1b_take", "A002", "S01", "1A", 1, 5.5, "medium", 0],
    ["01_1c_take", "A002", "S01", "1A", 1, 6.0, "medium", 0],
    ["03_2a_take", "A007", "S03", "2A", 1, 3.2, "wide", 0],
    ["03_2c_take", "A007", "S03", "2C", 3, 2.1, "medium_close", 0],
    ["03_2e_take", "A007", "S03", "2E", 5, 4.4, "wide", 0],
]


def _result(rows):
    result = MagicMock()
    result.column_names = COLUMNS
    result.result_rows = rows
    return result


@patch("ui.server.clip_list.client")
class TestClipList:
    def test_returns_all_clips_unfiltered(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        clips = clip_list()

        assert len(clips) == 6
        assert {c["clip_id"] for c in clips} == {r[0] for r in REAL_INDEX_ROWS}

    def test_circled_is_a_real_bool_not_the_raw_uint8(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        clips = clip_list()

        circled = {c["clip_id"]: c["circled"] for c in clips}
        assert circled["01_1a_take"] is True
        assert circled["01_1b_take"] is False

    def test_takes_are_not_a_unique_key_but_clip_id_is(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        clips = clip_list()
        s01 = [c for c in clips if c["scene"] == "S01"]

        assert len(s01) == 3
        assert all(c["take"] == 1 and c["slate"] == "1A" for c in s01)
        assert len({c["clip_id"] for c in s01}) == 3

    def test_filters_by_reel(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        clips = clip_list(reels=["A007"])

        assert {c["clip_id"] for c in clips} == {"03_2a_take", "03_2c_take", "03_2e_take"}

    def test_filters_by_multiple_reels_additively(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        clips = clip_list(reels=["A002", "A007"])

        assert len(clips) == 6

    def test_filters_by_shot_type_bucket_mapping_the_enum(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        clips = clip_list(shot_types=["MCU"])

        assert {c["clip_id"] for c in clips} == {"03_2c_take"}

    def test_filters_by_reel_and_shot_type_together(self, mock_client):
        mock_client.return_value.query.return_value = _result(REAL_INDEX_ROWS)

        clips = clip_list(reels=["A002"], shot_types=["WIDE"])

        assert clips == []
