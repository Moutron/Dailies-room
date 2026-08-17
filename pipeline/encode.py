"""Encode an uploaded frame sequence into a playable MP4."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# 24fps -- Tears of Steel's source frame rate (see agent/tools/search.py's FPS
# and ui/src/api.ts's FPS), used here only as a default. An assumption, not
# derived from clip metadata -- but unlike those two call sites, a frame
# sequence has no container-embedded rate at all, so the caller (the upload
# form) is allowed to override it if the shooter actually knows the capture
# rate.
DEFAULT_FPS = 24


class EncodeError(RuntimeError):
    """ffmpeg exited non-zero encoding a frame sequence to MP4; carries stderr."""


def _natural_key(path: Path) -> list[int | str]:
    """Zero-padded-aware sort key so frame_10.png doesn't land before frame_2.png."""
    return [int(chunk) if chunk.isdigit() else chunk for chunk in re.split(r"(\d+)", path.name)]


def frames_to_mp4(frame_paths: list[Path], out_path: Path, fps: int = DEFAULT_FPS) -> Path:
    """Encode a still-frame sequence into out_path, in natural filename order.

    Frames are copied (or symlinked, where the filesystem allows it) into a
    sequentially-numbered temp dir, since ffmpeg's image2 demuxer needs a
    contiguous %06d-style sequence and the frames may not already be named
    that way. `yuv420p` is required, not cosmetic -- without it the browser
    <video> tag will not decode the result.
    """
    if not frame_paths:
        raise EncodeError("no frames given to encode")

    ordered = sorted(frame_paths, key=_natural_key)
    ext = ordered[0].suffix.lstrip(".").lower()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for i, frame in enumerate(ordered, start=1):
            dest = tmp_dir / f"{i:06d}.{ext}"
            try:
                dest.symlink_to(frame.resolve())
            except OSError:
                shutil.copy(frame, dest)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(tmp_dir / f"%06d.{ext}"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(out_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise EncodeError(result.stderr)

    return out_path
