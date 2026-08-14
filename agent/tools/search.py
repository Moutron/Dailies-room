"""Search over the footage index. Hybrid: semantic + filters."""

import logging

from google.adk.tools import ToolContext

from agent import config
from agent.tools._errors import reports_index_errors
from agent.tools._evidence import run_query
from pipeline.embed import embed_batch
from pipeline.ingest import client

logger = logging.getLogger(__name__)


@reports_index_errors
def search_dialogue(
    query: str,
    limit: int = 8,
    scene: str | None = None,
    speaker: str | None = None,
    tool_context: ToolContext | None = None,
) -> list[dict]:
    """Find spoken lines matching a description, meaning-based not keyword.

    Use for questions about what was said or how it was performed.

    Args:
        query: What you're looking for, in plain language.
        limit: Max results.
        scene: Optionally restrict to a scene, e.g. "S12".
        speaker: Optionally restrict to one character.

    Returns:
        Matching lines with clip_id, reel, source timecode, speaker, text
        and delivery.
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
               speaker, text, delivery, intensity, reel, tc_start_s,
               cosineDistance(embedding, %(vec)s) AS distance
        FROM {config.CH_DATABASE}.dialogue
        {clause}
        ORDER BY distance ASC
        LIMIT %(limit)s
    """
    call_id = tool_context.function_call_id if tool_context else None
    result = run_query(client(), call_id, "dialogue", sql, params)
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
    for row in rows:
        offset = row.pop("tc_start_s")
        row["timecode_in"] = timecode(row["start_s"], offset)
        row["timecode_out"] = timecode(row["end_s"], offset)
    logger.info(
        "search_dialogue",
        extra={"query": query, "results": len(rows), "scene": scene, "speaker": speaker},
    )
    return rows


@reports_index_errors
def search_visuals(
    query: str,
    limit: int = 8,
    shot_type: str | None = None,
    tool_context: ToolContext | None = None,
) -> list[dict]:
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
               notable_elements, reel, tc_start_s,
               cosineDistance(embedding, %(vec)s) AS distance
        FROM {config.CH_DATABASE}.visuals
        {clause}
        ORDER BY distance ASC
        LIMIT %(limit)s
    """
    call_id = tool_context.function_call_id if tool_context else None
    result = run_query(client(), call_id, "visuals", sql, params)
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
    for row in rows:
        offset = row.pop("tc_start_s")
        row["timecode_in"] = timecode(row["start_s"], offset)
        row["timecode_out"] = timecode(row["end_s"], offset)
    logger.info(
        "search_visuals",
        extra={"query": query, "results": len(rows), "shot_type": shot_type},
    )
    return rows


FPS = 24


def timecode(seconds: float, offset_s: float = 0.0, fps: int = FPS) -> str:
    """Seconds from clip start -> HH:MM:SS:FF, the format an editor actually reads.

    `offset_s` is the clip's source timecode at frame zero (`tc_start_s`).
    Without it this returns a clip-relative range that resets to
    00:00:00:00 for every clip — useless for finding the shot on the
    actual card, and indistinguishable from every other result.
    """
    total_frames = round((seconds + offset_s) * fps)
    frames = total_frames % fps
    total_seconds = total_frames // fps
    return (
        f"{total_seconds // 3600:02d}:"
        f"{(total_seconds % 3600) // 60:02d}:"
        f"{total_seconds % 60:02d}:"
        f"{frames:02d}"
    )
