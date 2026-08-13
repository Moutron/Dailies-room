"""Load processed clip JSON into ClickHouse."""

import json
import subprocess
import threading
from pathlib import Path

import clickhouse_connect

from agent import config
from pipeline.embed import dialogue_text, embed_batch, visual_text

CLIPS_DIR = Path("data/clips")

# agent/tools/search.py, coverage.py, and takes.py each call client() once per
# tool invocation; under ui/server, that used to mean a brand-new HTTP
# connection (TCP + TLS handshake) per request. clickhouse-connect's client
# wraps a requests.Session, which requests' own docs don't guarantee is safe
# to share across threads -- and FastAPI runs sync path operations (and,
# through them, ADK's sync tool calls) in a thread pool, so a single shared
# global instance isn't safe here. A thread-local cache reuses the connection
# across requests handled by the same worker thread without sharing a session
# across threads. Same rotation caveat as config.py's `_secret()` @lru_cache
# (see docs/RUNBOOK.md's "Secret rotation" section): a client built with a
# since-rotated password keeps using it until this thread's cached client is
# gone (process restart, or thread pool churn).
_local = threading.local()


def client():
    if not hasattr(_local, "ch"):
        _local.ch = clickhouse_connect.get_client(
            host=config.CH_HOST,
            port=config.CH_PORT,
            username=config.CH_USER,
            password=config.ch_password(),
            database=config.CH_DATABASE,
            secure=config.CH_SECURE,
        )
    return _local.ch


def clip_duration_s(clip_id: str) -> float | None:
    """Actual duration of the source file, ground truth for clamping.

    Gemini's segment timestamps are estimates and can run past the real
    clip length (observed: reporting ~9s for clips that are actually 5s).
    ffprobe reads the container header, so it isn't a guess.
    """
    path = CLIPS_DIR / f"{clip_id}.mp4"
    if not path.exists():
        return None
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None


def _clamp(seconds: float, duration: float | None) -> float:
    """Keep a model-estimated timestamp from running past the real clip."""
    if duration is None:
        return seconds
    return min(seconds, duration)


def ingest_all() -> None:
    ch = client()
    manifest_clips = json.loads(Path("data/manifest.json").read_text())["clips"]
    manifest = {m["clip_id"]: m for m in manifest_clips}

    clip_rows, dialogue_rows, visual_rows = [], [], []

    for path in sorted(Path("data/processed").glob("*.json")):
        analysis = json.loads(path.read_text())
        clip_id = analysis["clip_id"]
        meta = manifest.get(clip_id, {})
        duration = clip_duration_s(clip_id)

        clip_rows.append(
            [
                clip_id,
                meta.get("source", ""),
                meta.get("scene", ""),
                meta.get("slate", ""),
                meta.get("take", 0),
                meta.get("location", ""),
                meta.get("day_night", ""),
                meta.get("int_ext", ""),
                duration or 0.0,
                analysis["summary"],
                analysis["dominant_mood"],
                analysis["characters_present"],
                meta.get("characters_expected", []),
                analysis["technical_notes"],
                f"gs://{config.GCS_BUCKET}/clips/{clip_id}.mp4",
                meta.get("reel", ""),
                meta.get("tc_start_s", 0.0),
            ]
        )

        # Embed in batches per clip — one call per clip, not per segment.
        dlg = analysis["dialogue"]
        if dlg:
            vecs = embed_batch([dialogue_text(s) for s in dlg])
            for i, (seg, vec) in enumerate(zip(dlg, vecs)):
                dialogue_rows.append(
                    [
                        clip_id,
                        i,
                        meta.get("scene", ""),
                        meta.get("take", 0),
                        _clamp(seg["start_s"], duration),
                        _clamp(seg["end_s"], duration),
                        seg["speaker"],
                        seg["text"],
                        seg["delivery"],
                        seg["intensity"],
                        meta.get("reel", ""),
                        meta.get("tc_start_s", 0.0),
                        vec,
                    ]
                )

        vis = analysis["visuals"]
        if vis:
            vecs = embed_batch([visual_text(s) for s in vis])
            for i, (seg, vec) in enumerate(zip(vis, vecs)):
                visual_rows.append(
                    [
                        clip_id,
                        i,
                        meta.get("scene", ""),
                        meta.get("take", 0),
                        _clamp(seg["start_s"], duration),
                        _clamp(seg["end_s"], duration),
                        seg["description"],
                        seg["shot_type"],
                        seg["camera_movement"],
                        seg["characters_visible"],
                        seg["notable_elements"],
                        meta.get("reel", ""),
                        meta.get("tc_start_s", 0.0),
                        vec,
                    ]
                )

    clip_columns = [
        "clip_id",
        "source",
        "scene",
        "slate",
        "take",
        "location",
        "day_night",
        "int_ext",
        "duration_s",
        "summary",
        "dominant_mood",
        "characters_present",
        "characters_expected",
        "technical_notes",
        "gcs_uri",
        "reel",
        "tc_start_s",
    ]
    dialogue_columns = [
        "clip_id",
        "segment_idx",
        "scene",
        "take",
        "start_s",
        "end_s",
        "speaker",
        "text",
        "delivery",
        "intensity",
        "reel",
        "tc_start_s",
        "embedding",
    ]
    visual_columns = [
        "clip_id",
        "segment_idx",
        "scene",
        "take",
        "start_s",
        "end_s",
        "description",
        "shot_type",
        "camera_movement",
        "characters_visible",
        "notable_elements",
        "reel",
        "tc_start_s",
        "embedding",
    ]

    # Insert, then merge duplicates away — no TRUNCATE. All three tables are
    # ReplacingMergeTree(ingested_at) keyed on their ORDER BY (e.g. clips on
    # (scene, slate, take)): re-ingesting a clip inserts a new-dated row
    # rather than requiring the table to go empty first, so a concurrent
    # read never sees a momentarily-empty index the way it could with
    # TRUNCATE-then-insert. `OPTIMIZE ... FINAL` forces the merge (and thus
    # the dedup) to happen synchronously here rather than waiting on
    # ClickHouse's background merge schedule, so a query run right after
    # ingest_all() returns sees exactly one row per key, same as before.
    #
    # Caveat: dialogue/visuals key on (scene, clip_id, start_s), not
    # segment_idx — if a re-run of Gemini analysis shifts a segment's
    # start_s, the old segment isn't recognized as "the same row" and both
    # survive as distinct rows instead of one replacing the other. Not an
    # issue for a stable, already-reviewed data/processed/ (this project's
    # actual usage), but worth knowing before re-running video analysis
    # against a live index.
    if clip_rows:
        ch.insert("clips", clip_rows, column_names=clip_columns)
    if dialogue_rows:
        ch.insert("dialogue", dialogue_rows, column_names=dialogue_columns)
    if visual_rows:
        ch.insert("visuals", visual_rows, column_names=visual_columns)
    for table in ("clips", "dialogue", "visuals"):
        ch.command(f"OPTIMIZE TABLE {config.CH_DATABASE}.{table} FINAL")

    print(
        f"Ingested {len(clip_rows)} clips, {len(dialogue_rows)} lines, "
        f"{len(visual_rows)} visual segments."
    )


if __name__ == "__main__":
    ingest_all()
