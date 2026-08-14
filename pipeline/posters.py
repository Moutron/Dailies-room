"""Extract a mid-clip poster frame per clip for the UI.

One representative frame per clip, letterboxed to 16:9 at 960px wide (the
clip-detail viewer renders it at up to 456px, cards at 190px — 960px covers
both with headroom for a HiDPI screen). The two reels have different source
aspect ratios — S03 is 4096x2160 (~1.9:1), S01 is 1280x534 (~2.4:1, wider
than 16:9) — so a center crop would cut real image content out of frame on
the S01 reel. Letterboxing (scale-to-fit + pad) is used instead, consistently
across both, so a poster is always the whole shot.

There is no existing script that produced data/thumbs/'s contact-strip
frames — they were extracted by hand with the same ffmpeg approach this
script formalizes. This is the reproducible version for posters; thumbs are
unaffected and out of scope here.
"""

import subprocess
from pathlib import Path

from pipeline.ingest import CLIPS_DIR, clip_duration_s

POSTERS_DIR = Path("data/posters")
POSTER_WIDTH = 960
POSTER_HEIGHT = 540  # 16:9


def extract_poster(clip_id: str, out_dir: Path = POSTERS_DIR) -> Path:
    """Writes {out_dir}/{clip_id}.jpg from the frame at the clip's midpoint."""
    duration = clip_duration_s(clip_id)
    if duration is None:
        raise FileNotFoundError(f"no source clip for {clip_id!r} in {CLIPS_DIR}")
    midpoint = duration / 2

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{clip_id}.jpg"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{midpoint:.3f}",
            "-i",
            str(CLIPS_DIR / f"{clip_id}.mp4"),
            "-frames:v",
            "1",
            "-vf",
            (
                f"scale={POSTER_WIDTH}:{POSTER_HEIGHT}:force_original_aspect_ratio=decrease,"
                f"pad={POSTER_WIDTH}:{POSTER_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black"
            ),
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


def extract_all_posters(out_dir: Path = POSTERS_DIR) -> list[Path]:
    return [extract_poster(path.stem, out_dir) for path in sorted(CLIPS_DIR.glob("*.mp4"))]


if __name__ == "__main__":
    for written in extract_all_posters():
        print(f"wrote {written}")
