"""Search over the footage index. Hybrid: semantic + filters."""

from pipeline.embed import embed_batch
from pipeline.ingest import client


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
        FROM dailies.dialogue
        {clause}
        ORDER BY distance ASC
        LIMIT %(limit)s
    """
    result = client().query(sql, parameters=params)
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


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
        FROM dailies.visuals
        {clause}
        ORDER BY distance ASC
        LIMIT %(limit)s
    """
    result = client().query(sql, parameters=params)
    return [dict(zip(result.column_names, row)) for row in result.result_rows]
