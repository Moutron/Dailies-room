"""Tests for ui/server/circle.py -- the product's first write path."""

from unittest.mock import MagicMock, patch

from ui.server.circle import clip_exists, set_circled


def _count_result(n: int):
    result = MagicMock()
    result.result_rows = [(n,)]
    return result


@patch("ui.server.circle.client")
class TestClipExists:
    def test_true_when_the_clip_is_indexed(self, mock_client):
        mock_client.return_value.query.return_value = _count_result(1)

        assert clip_exists("01_1a_take") is True

    def test_false_when_the_clip_is_not_indexed(self, mock_client):
        mock_client.return_value.query.return_value = _count_result(0)

        assert clip_exists("does_not_exist") is False


@patch("ui.server.circle.client")
class TestSetCircled:
    def test_returns_none_for_an_unindexed_clip_without_writing(self, mock_client):
        mock_client.return_value.query.return_value = _count_result(0)

        result = set_circled("does_not_exist", True)

        assert result is None
        mock_client.return_value.insert.assert_not_called()

    def test_inserts_a_real_row_and_returns_the_new_state(self, mock_client):
        mock_client.return_value.query.return_value = _count_result(1)

        result = set_circled("01_1a_take", True)

        assert result == {"clip_id": "01_1a_take", "circled": True}
        call = mock_client.return_value.insert.call_args
        assert call[0][0] == "circled_takes"
        assert call[1]["column_names"] == ["clip_id", "circled", "updated_at"]
        row = call[0][1][0]
        assert row[:2] == ["01_1a_take", 1]

    def test_uncircling_inserts_a_zero_row_not_a_delete(self, mock_client):
        mock_client.return_value.query.return_value = _count_result(1)

        set_circled("01_1a_take", False)

        call = mock_client.return_value.insert.call_args
        row = call[0][1][0]
        assert row[:2] == ["01_1a_take", 0]

    def test_updated_at_is_written_explicitly_never_left_to_the_column_default(self, mock_client):
        # Confirmed live: this table's engine (ClickHouse Cloud's
        # SharedReplacingMergeTree) deduplicates inserts by hashing the
        # submitted block, before server-side DEFAULT now64(3) is applied --
        # so re-circling a clip to a value it already held submitted an
        # identical (clip_id, circled) tuple and was silently dropped. A
        # real, explicit updated_at makes every insert's block distinct.
        mock_client.return_value.query.return_value = _count_result(1)

        set_circled("01_1a_take", True)
        first = mock_client.return_value.insert.call_args[0][1][0][2]
        mock_client.return_value.insert.reset_mock()
        set_circled("01_1a_take", True)
        second = mock_client.return_value.insert.call_args[0][1][0][2]

        assert first != second
