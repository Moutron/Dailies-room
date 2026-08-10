"""Load processed clip JSON into ClickHouse."""

import json
from pathlib import Path

import clickhouse_connect

from agent import config
from pipeline.embed import dialogue_text, embed_batch, visual_text


def client():
    return clickhouse_connect.get_client(
        host=config.CH_HOST,
        port=config.CH_PORT,
        username=config.CH_USER,
        password=config.ch_password(),
        database=config.CH_DATABASE,
        secure=True,
    )


def ingest_all() -> None:
    ch = client()
    manifest = {m["clip_id"]: m for m in json.loads(Path("data/manifest.json").read_text())}

    clip_rows, dialogue_rows, visual_rows = [], [], []

    for path in sorted(Path("data/processed").glob("*.json")):
        analysis = json.loads(path.read_text())
        clip_id = analysis["clip_id"]
        meta = manifest.get(clip_id, {})

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
                0.0,
                analysis["summary"],
                analysis["dominant_mood"],
                analysis["characters_present"],
                meta.get("characters_expected", []),
                analysis["technical_notes"],
                f"gs://{config.GCS_BUCKET}/clips/{clip_id}.mp4",
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
                        seg["start_s"],
                        seg["end_s"],
                        seg["speaker"],
                        seg["text"],
                        seg["delivery"],
                        seg["intensity"],
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
                        seg["start_s"],
                        seg["end_s"],
                        seg["description"],
                        seg["shot_type"],
                        seg["camera_movement"],
                        seg["characters_visible"],
                        seg["notable_elements"],
                        vec,
                    ]
                )

    # Truncate then insert: ingest is idempotent, so a re-run is always safe.
    for table in ("clips", "dialogue", "visuals"):
        ch.command(f"TRUNCATE TABLE IF EXISTS {config.CH_DATABASE}.{table}")

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
    ]
    if clip_rows:
        ch.insert("clips", clip_rows, column_names=clip_columns)
    if dialogue_rows:
        ch.insert("dialogue", dialogue_rows, column_names="*")
    if visual_rows:
        ch.insert("visuals", visual_rows, column_names="*")

    print(
        f"Ingested {len(clip_rows)} clips, {len(dialogue_rows)} lines, "
        f"{len(visual_rows)} visual segments."
    )


if __name__ == "__main__":
    ingest_all()
