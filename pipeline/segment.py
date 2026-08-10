"""Cut a long file into clips at specified boundaries.

Kept deliberately simple: an explicit cut list beats automatic scene detection
here, because you want clips that correspond to meaningful production units
(a scene, a setup), not to every camera move.
"""

import subprocess
from pathlib import Path

# (clip_id, start, end, scene, description)
CUT_LIST = [
    ("TOS_S01_01", "00:00:12", "00:00:48", "S01", "Bridge - Thom and Celia argue"),
    ("TOS_S01_02", "00:00:48", "00:01:20", "S01", "Bridge - Celia leaves"),
    # ... fill in from watching the film
]

# Same setup, three takes. Same cut list gets applied to each one so you
# can compare takes clip-by-clip.
TAKES = [
    Path("data/03_2a_take.mp4"),
    Path("data/03_2c_take.mp4"),
    Path("data/03_2e_take.mp4"),
]


def cut(source: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    take_name = source.stem  # e.g. "03_2a_take"
    for clip_id, start, end, _scene, _desc in CUT_LIST:
        out = out_dir / f"{clip_id}__{take_name}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-ss",
                start,
                "-to",
                end,
                # Re-encode rather than stream-copy: keyframe-aligned copies
                # drift, and drifting timecodes poison everything downstream.
                "-c:v",
                "libx264",
                "-crf",
                "20",
                "-c:a",
                "aac",
                str(out),
            ],
            check=True,
        )
        print(f"wrote {out}")


if __name__ == "__main__":
    for take in TAKES:
        cut(take, Path("data/clips"))
