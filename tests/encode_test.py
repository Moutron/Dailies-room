"""Tests for pipeline/encode.py's frame-sequence-to-mp4 encoder."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline.encode import EncodeError, _natural_key, frames_to_mp4


class TestNaturalKey:
    def test_zero_padded_aware_ordering(self):
        names = ["frame_10.png", "frame_2.png", "frame_1.png"]
        ordered = sorted((Path(n) for n in names), key=_natural_key)
        assert [p.name for p in ordered] == ["frame_1.png", "frame_2.png", "frame_10.png"]


class TestFramesToMp4:
    def test_raises_when_no_frames_given(self, tmp_path):
        with pytest.raises(EncodeError, match="no frames"):
            frames_to_mp4([], tmp_path / "out.mp4")

    def test_encodes_frames_in_natural_order(self, tmp_path):
        frame_paths = []
        for name, content in [
            ("frame_10.png", b"ten"),
            ("frame_2.png", b"two"),
            ("frame_1.png", b"one"),
        ]:
            p = tmp_path / name
            p.write_bytes(content)
            frame_paths.append(p)
        out_path = tmp_path / "out.mp4"

        captured = {}

        def fake_run(args, **kwargs):
            # Inspect the sequenced temp dir *while it still exists* --
            # frames_to_mp4's TemporaryDirectory is torn down before this
            # function returns.
            input_pattern = args[args.index("-i") + 1]
            tmp_dir = Path(input_pattern).parent
            captured["order"] = [(tmp_dir / f"{i:06d}.png").read_bytes() for i in (1, 2, 3)]
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        with patch("pipeline.encode.subprocess.run", side_effect=fake_run):
            result = frames_to_mp4(frame_paths, out_path, fps=12)

        assert result == out_path
        # frame_1 (one) < frame_2 (two) < frame_10 (ten) in natural order.
        assert captured["order"] == [b"one", b"two", b"ten"]

    def test_passes_fps_and_required_flags_to_ffmpeg(self, tmp_path):
        frame = tmp_path / "frame_1.jpg"
        frame.write_bytes(b"x")
        out_path = tmp_path / "out.mp4"

        with patch("pipeline.encode.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            frames_to_mp4([frame], out_path, fps=30)

        args = mock_run.call_args.args[0]
        assert args[0] == "ffmpeg"
        assert "-framerate" in args
        assert args[args.index("-framerate") + 1] == "30"
        assert "-pix_fmt" in args
        assert args[args.index("-pix_fmt") + 1] == "yuv420p"
        assert "+faststart" in args

    def test_raises_encode_error_with_stderr_on_ffmpeg_failure(self, tmp_path):
        frame = tmp_path / "frame_1.jpg"
        frame.write_bytes(b"x")
        out_path = tmp_path / "out.mp4"

        with patch("pipeline.encode.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="ffmpeg: unsupported codec"
            )
            with pytest.raises(EncodeError, match="unsupported codec"):
                frames_to_mp4([frame], out_path)

    def test_creates_the_output_directory(self, tmp_path):
        frame = tmp_path / "frame_1.jpg"
        frame.write_bytes(b"x")
        out_path = tmp_path / "nested" / "out.mp4"

        with patch("pipeline.encode.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            frames_to_mp4([frame], out_path)

        assert out_path.parent.is_dir()
