"""Tests for pipeline/ingest.py's pure/ffprobe-adjacent helpers."""

import json
import subprocess
from unittest.mock import MagicMock, patch

from pipeline.ingest import (
    CLIP_COLUMNS,
    DIALOGUE_COLUMNS,
    VISUAL_COLUMNS,
    _clamp,
    build_rows,
    clip_duration_s,
    ingest_all,
    insert_rows,
)


class TestClamp:
    def test_no_duration_known_returns_seconds_unchanged(self):
        assert _clamp(9.0, None) == 9.0

    def test_seconds_within_duration_unchanged(self):
        assert _clamp(3.0, 5.0) == 3.0

    def test_seconds_past_duration_clamped(self):
        assert _clamp(9.0, 5.0) == 5.0

    def test_seconds_equal_to_duration(self):
        assert _clamp(5.0, 5.0) == 5.0


class TestClipDurationS:
    def test_missing_file_returns_none(self, tmp_path):
        with patch("pipeline.ingest.CLIPS_DIR", tmp_path):
            assert clip_duration_s("does_not_exist") is None

    def test_reads_ffprobe_stdout(self, tmp_path):
        clip_path = tmp_path / "clip_1.mp4"
        clip_path.write_bytes(b"not a real video, just needs to exist")
        with (
            patch("pipeline.ingest.CLIPS_DIR", tmp_path),
            patch("pipeline.ingest.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="5.033000\n", stderr=""
            )
            assert clip_duration_s("clip_1") == 5.033

    def test_ffprobe_failure_returns_none(self, tmp_path):
        clip_path = tmp_path / "clip_1.mp4"
        clip_path.write_bytes(b"junk")
        with (
            patch("pipeline.ingest.CLIPS_DIR", tmp_path),
            patch("pipeline.ingest.subprocess.run") as mock_run,
        ):
            mock_run.side_effect = subprocess.CalledProcessError(1, "ffprobe")
            assert clip_duration_s("clip_1") is None

    def test_ffprobe_unparseable_output_returns_none(self, tmp_path):
        clip_path = tmp_path / "clip_1.mp4"
        clip_path.write_bytes(b"junk")
        with (
            patch("pipeline.ingest.CLIPS_DIR", tmp_path),
            patch("pipeline.ingest.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="N/A\n", stderr=""
            )
            assert clip_duration_s("clip_1") is None


class TestBuildRows:
    def test_builds_one_clip_row_and_matching_dialogue_visual_rows(self):
        analysis = {
            "clip_id": "clip_1",
            "summary": "A person walks across a bridge.",
            "dominant_mood": "tense",
            "characters_present": ["ELI"],
            "technical_notes": ["boom in frame"],
            "dialogue": [
                {
                    "start_s": 0.0,
                    "end_s": 9.0,
                    "speaker": "ELI",
                    "text": "hi",
                    "delivery": "flat",
                    "intensity": 0.1,
                }
            ],
            "visuals": [
                {
                    "start_s": 0.0,
                    "end_s": 9.0,
                    "description": "a wide shot",
                    "shot_type": "wide",
                    "camera_movement": "static",
                    "characters_visible": ["ELI"],
                    "notable_elements": ["rifle"],
                }
            ],
        }
        meta = {
            "scene": "S01",
            "slate": "1A",
            "take": 2,
            "reel": "A001",
            "tc_start_s": 3600.0,
            "characters_expected": ["ELI"],
        }

        with patch("pipeline.ingest.embed_batch", return_value=[[0.1] * 3072]) as mock_embed:
            clip_rows, dialogue_rows, visual_rows = build_rows(analysis, meta, duration=5.0)

        assert mock_embed.call_count == 2  # once for dialogue, once for visuals
        assert len(clip_rows) == 1
        clip_row = dict(zip(CLIP_COLUMNS, clip_rows[0]))
        assert clip_row["clip_id"] == "clip_1"
        assert clip_row["take"] == 2
        assert clip_row["duration_s"] == 5.0  # real duration, not clamped from an estimate
        assert clip_row["reel"] == "A001"

        assert len(dialogue_rows) == 1
        dialogue_row = dict(zip(DIALOGUE_COLUMNS, dialogue_rows[0]))
        assert dialogue_row["end_s"] == 5.0  # clamped: Gemini said 9.0, real duration is 5.0
        assert dialogue_row["embedding"] == [0.1] * 3072

        assert len(visual_rows) == 1
        visual_row = dict(zip(VISUAL_COLUMNS, visual_rows[0]))
        assert visual_row["end_s"] == 5.0

    def test_empty_dialogue_and_visuals_skip_embedding_entirely(self):
        analysis = {
            "clip_id": "clip_1",
            "summary": "s",
            "dominant_mood": "m",
            "characters_present": [],
            "technical_notes": [],
            "dialogue": [],
            "visuals": [],
        }

        with patch("pipeline.ingest.embed_batch") as mock_embed:
            clip_rows, dialogue_rows, visual_rows = build_rows(analysis, {}, duration=None)

        mock_embed.assert_not_called()
        assert dialogue_rows == []
        assert visual_rows == []
        clip_row = dict(zip(CLIP_COLUMNS, clip_rows[0]))
        assert clip_row["duration_s"] == 0.0  # ingest_all()'s existing "no known duration" default
        assert clip_row["scene"] == ""  # meta.get(...) empty defaults, no invented metadata


class TestInsertRows:
    def test_inserts_each_nonempty_table_and_optimizes_all_three(self):
        with patch("pipeline.ingest.client") as mock_client_fn:
            mock_ch = MagicMock()
            mock_client_fn.return_value = mock_ch

            insert_rows([["clip_row"]], [["dialogue_row"]], [])

        mock_ch.insert.assert_any_call("clips", [["clip_row"]], column_names=CLIP_COLUMNS)
        mock_ch.insert.assert_any_call(
            "dialogue", [["dialogue_row"]], column_names=DIALOGUE_COLUMNS
        )
        assert mock_ch.insert.call_count == 2  # visuals skipped: empty
        assert mock_ch.command.call_count == 3  # OPTIMIZE ... FINAL on all three tables regardless

    def test_skips_insert_calls_for_empty_row_lists(self):
        with patch("pipeline.ingest.client") as mock_client_fn:
            mock_ch = MagicMock()
            mock_client_fn.return_value = mock_ch

            insert_rows([], [], [])

        mock_ch.insert.assert_not_called()
        assert mock_ch.command.call_count == 3


class TestIngestAllRefactor:
    def test_ingest_all_composes_build_rows_and_insert_rows_identically(
        self, tmp_path, monkeypatch
    ):
        """The refactor's whole point: ingest_all()'s output must be exactly
        what calling build_rows() + insert_rows() by hand on the same
        manifest/processed fixture would produce."""
        (tmp_path / "data" / "processed").mkdir(parents=True)
        manifest_clip = {
            "clip_id": "clip_1",
            "source": "cam1",
            "scene": "S01",
            "slate": "1A",
            "take": 1,
            "location": "canal",
            "day_night": "DAY",
            "int_ext": "EXT",
            "characters_expected": ["ELI"],
            "reel": "A001",
            "tc_start_s": 0.0,
        }
        (tmp_path / "data" / "manifest.json").write_text(json.dumps({"clips": [manifest_clip]}))

        analysis = {
            "clip_id": "clip_1",
            "summary": "s",
            "dominant_mood": "m",
            "characters_present": ["ELI"],
            "technical_notes": [],
            "dialogue": [
                {
                    "start_s": 0.0,
                    "end_s": 1.0,
                    "speaker": "ELI",
                    "text": "hi",
                    "delivery": "flat",
                    "intensity": 0.1,
                }
            ],
            "visuals": [
                {
                    "start_s": 0.0,
                    "end_s": 1.0,
                    "description": "d",
                    "shot_type": "wide",
                    "camera_movement": "static",
                    "characters_visible": ["ELI"],
                    "notable_elements": [],
                }
            ],
        }
        (tmp_path / "data" / "processed" / "clip_1.json").write_text(json.dumps(analysis))

        monkeypatch.chdir(tmp_path)

        with (
            patch("pipeline.ingest.embed_batch", return_value=[[0.1] * 3072]),
            patch("pipeline.ingest.insert_rows") as mock_insert,
        ):
            ingest_all()

        called_clip_rows, called_dialogue_rows, called_visual_rows = mock_insert.call_args.args

        with patch("pipeline.ingest.embed_batch", return_value=[[0.1] * 3072]):
            expected_clip_rows, expected_dialogue_rows, expected_visual_rows = build_rows(
                analysis, manifest_clip, duration=None
            )

        assert called_clip_rows == expected_clip_rows
        assert called_dialogue_rows == expected_dialogue_rows
        assert called_visual_rows == expected_visual_rows
