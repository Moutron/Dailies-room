"""Tests for pipeline/ingest.py's pure/ffprobe-adjacent helpers."""

import subprocess
from unittest.mock import patch

from pipeline.ingest import _clamp, clip_duration_s


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
