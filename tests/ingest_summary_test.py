"""Tests for ui/server/ingest.py's ingest_summary()."""

from unittest.mock import MagicMock, patch

from ui.server.ingest import ingest_summary

CLIP_COLUMNS = ["clip_id", "duration_s", "ingested_at", "dialogue_count"]

# The real six-clip index:
# S01 clips have 1/2/1 dialogue lines post the timing fix, S03 clips have 0.
REAL_INDEX_ROWS = [
    ["03_2e_take", 5.8, "2026-08-12 21:50:10", 0],
    ["03_2c_take", 5.2, "2026-08-12 21:49:40", 0],
    ["03_2a_take", 4.9, "2026-08-12 21:49:05", 0],
    ["01_1c_take", 4.4, "2026-08-12 21:47:55", 1],
    ["01_1b_take", 4.7, "2026-08-12 21:47:20", 2],
    ["01_1a_take", 4.9, "2026-08-12 21:46:40", 1],
]


def _clips_result(rows):
    result = MagicMock()
    result.column_names = CLIP_COLUMNS
    result.result_rows = rows
    return result


def _scalar(value):
    result = MagicMock()
    result.result_rows = [(value,)]
    return result


@patch("ui.server.ingest.index_stats")
@patch("ui.server.ingest.client")
class TestIngestSummary:
    def test_every_clip_is_ready_no_in_flight_or_queued_state(self, mock_client, mock_index_stats):
        mock_client.return_value.query.side_effect = [
            _clips_result(REAL_INDEX_ROWS),
            _scalar(4),  # dialogue count
            _scalar(6),  # visuals count
        ]
        mock_index_stats.return_value = {"clip_count": 6, "total_duration_s": 29.9}

        summary = ingest_summary()

        assert len(summary["clips"]) == 6
        assert all(c["state"] == "READY" for c in summary["clips"])

    def test_real_dialogue_counts_survive_into_the_clip_rows(self, mock_client, mock_index_stats):
        mock_client.return_value.query.side_effect = [
            _clips_result(REAL_INDEX_ROWS),
            _scalar(4),
            _scalar(6),
        ]
        mock_index_stats.return_value = {"clip_count": 6, "total_duration_s": 29.9}

        summary = ingest_summary()

        by_id = {c["clip_id"]: c for c in summary["clips"]}
        assert by_id["01_1b_take"]["dialogue_count"] == 2
        assert by_id["03_2a_take"]["dialogue_count"] == 0

    def test_embeddings_is_the_real_sum_of_dialogue_and_visuals_rows(
        self, mock_client, mock_index_stats
    ):
        mock_client.return_value.query.side_effect = [
            _clips_result(REAL_INDEX_ROWS),
            _scalar(4),
            _scalar(6),
        ]
        mock_index_stats.return_value = {"clip_count": 6, "total_duration_s": 29.9}

        summary = ingest_summary()

        assert summary["embeddings"] == 10

    def test_indexed_today_reuses_index_stats_clip_count(self, mock_client, mock_index_stats):
        mock_client.return_value.query.side_effect = [
            _clips_result(REAL_INDEX_ROWS),
            _scalar(4),
            _scalar(6),
        ]
        mock_index_stats.return_value = {"clip_count": 6, "total_duration_s": 29.9}

        summary = ingest_summary()

        assert summary["indexed_today"] == 6
        mock_index_stats.assert_called_once()

    def test_most_recent_ingested_at_is_the_first_row_real_index_orders_desc(
        self, mock_client, mock_index_stats
    ):
        mock_client.return_value.query.side_effect = [
            _clips_result(REAL_INDEX_ROWS),
            _scalar(4),
            _scalar(6),
        ]
        mock_index_stats.return_value = {"clip_count": 6, "total_duration_s": 29.9}

        summary = ingest_summary()

        assert summary["most_recent_ingested_at"] == "2026-08-12 21:50:10"

    def test_empty_index_has_no_most_recent_timestamp(self, mock_client, mock_index_stats):
        mock_client.return_value.query.side_effect = [
            _clips_result([]),
            _scalar(0),
            _scalar(0),
        ]
        mock_index_stats.return_value = {"clip_count": 0, "total_duration_s": 0.0}

        summary = ingest_summary()

        assert summary["most_recent_ingested_at"] is None
        assert summary["clips"] == []
