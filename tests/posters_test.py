"""Tests for pipeline/posters.py."""

from unittest.mock import patch

import pytest

from pipeline.posters import extract_all_posters, extract_poster


class TestExtractPoster:
    def test_raises_when_source_clip_is_missing(self, tmp_path):
        with (
            patch("pipeline.posters.clip_duration_s", return_value=None),
            pytest.raises(FileNotFoundError, match="clip_1"),
        ):
            extract_poster("clip_1", out_dir=tmp_path)

    def test_calls_ffmpeg_at_the_midpoint_and_returns_the_output_path(self, tmp_path):
        with (
            patch("pipeline.posters.clip_duration_s", return_value=6.0),
            patch("pipeline.posters.subprocess.run") as mock_run,
        ):
            out = extract_poster("clip_1", out_dir=tmp_path)

        assert out == tmp_path / "clip_1.jpg"
        args = mock_run.call_args.args[0]
        assert args[0] == "ffmpeg"
        assert "-ss" in args
        assert args[args.index("-ss") + 1] == "3.000"
        assert any("scale=960:540" in a for a in args)
        assert any("pad=960:540" in a for a in args)

    def test_creates_the_output_directory(self, tmp_path):
        out_dir = tmp_path / "nested" / "posters"
        with (
            patch("pipeline.posters.clip_duration_s", return_value=4.0),
            patch("pipeline.posters.subprocess.run"),
        ):
            extract_poster("clip_1", out_dir=out_dir)

        assert out_dir.is_dir()


class TestExtractAllPosters:
    def test_extracts_one_poster_per_clip_in_clips_dir(self, tmp_path):
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()
        (clips_dir / "clip_a.mp4").write_bytes(b"x")
        (clips_dir / "clip_b.mp4").write_bytes(b"x")
        out_dir = tmp_path / "posters"

        with (
            patch("pipeline.posters.CLIPS_DIR", clips_dir),
            patch("pipeline.posters.clip_duration_s", return_value=5.0),
            patch("pipeline.posters.subprocess.run"),
        ):
            written = extract_all_posters(out_dir=out_dir)

        assert sorted(p.name for p in written) == ["clip_a.jpg", "clip_b.jpg"]
