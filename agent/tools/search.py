"""Search over the footage index. Hybrid: semantic + filters."""

import logging

from agent import config
from agent.tools._errors import reports_index_errors
from pipeline.embed import embed_batch
from pipeline.ingest import client

logger = logging.getLogger(__name__)


@reports_index_errors
def search_dialogue(
    query: str,
    limit: int = 8,
    scene: str | None = None,
    speaker: str | None = None,
) -> list[dict]:
    """Find spoken lines matching a description, meaning-based not keyword.

    Use for questions about what was said or how it was performed.

    Args:
        query: What you're looking for, in plain language.
        limit: Max results.
        scene: Optionally restrict to a scene, e.g. "S12".
        speaker: Optionally restrict to one character.

    Returns:
        Matching lines with clip_id, timecode, speaker, text and delivery.
    """
    vec = embed_batch([query])[0]

    where = []
    params: dict = {"vec": vec, "limit": limit}
    if scene:
        where.append("scene = %(scene)s")
        params["scene"] = scene
    if speaker:
        where.append("speaker ILIKE %(speaker)s")
        params["speaker"] = f"%{speaker}%"
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    sql = f"""
        SELECT clip_id, scene, take, start_s, end_s,
               speaker, text, delivery, intensity,
               cosineDistance(embedding, %(vec)s) AS distance
        FROM {config.CH_DATABASE}.dialogue
        {clause}
        ORDER BY distance ASC
        LIMIT %(limit)s
    """
    result = client().query(sql, parameters=params)
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
    for row in rows:
        row["timecode_in"] = timecode(row["start_s"])
        row["timecode_out"] = timecode(row["end_s"])
    logger.info(
        "search_dialogue",
        extra={"query": query, "results": len(rows), "scene": scene, "speaker": speaker},
    )
    return rows


@reports_index_errors
def search_visuals(query: str, limit: int = 8, shot_type: str | None = None) -> list[dict]:
    """Find shots matching a visual description.

    Use for questions about what is on screen — framing, action, props,
    wardrobe, location.

    Args:
        query: What you're looking for, in plain language.
        limit: Max results.
        shot_type: Optionally filter, e.g. "close", "wide".
    """
    vec = embed_batch([query])[0]
    params: dict = {"vec": vec, "limit": limit}
    clause = ""
    if shot_type:
        clause = "WHERE shot_type = %(shot_type)s"
        params["shot_type"] = shot_type

    sql = f"""
        SELECT clip_id, scene, take, start_s, end_s, description,
               shot_type, camera_movement, characters_visible,
               notable_elements,
               cosineDistance(embedding, %(vec)s) AS distance
        FROM {config.CH_DATABASE}.visuals
        {clause}
        ORDER BY distance ASC
        LIMIT %(limit)s
    """
    result = client().query(sql, parameters=params)
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
    for row in rows:
        row["timecode_in"] = timecode(row["start_s"])
        row["timecode_out"] = timecode(row["end_s"])
    logger.info(
        "search_visuals",
        extra={"query": query, "results": len(rows), "shot_type": shot_type},
    )
    return rows


FPS = 24


def timecode(seconds: float, fps: int = FPS) -> str:
    """Seconds -> HH:MM:SS:FF, the format an editor actually reads."""
    total_frames = round(seconds * fps)
    frames = total_frames % fps
    total_seconds = total_frames // fps
    return (
        f"{total_seconds // 3600:02d}:"
        f"{(total_seconds % 3600) // 60:02d}:"
        f"{total_seconds % 60:02d}:"
        f"{frames:02d}"
    )
