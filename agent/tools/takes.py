"""Compare takes of the same setup."""

import logging

from agent import config
from agent.tools._errors import reports_index_errors
from agent.tools.search import timecode
from pipeline.embed import embed_batch
from pipeline.ingest import client

logger = logging.getLogger(__name__)

# Untuned: chosen by inspection, not validated against real repeated-line
# data, because the only ingested footage (S03, silent) has zero dialogue
# rows to test against. Revisit once dialogue with deliberately varied
# reads of the same line has been ingested.
LINE_MATCH_DISTANCE_THRESHOLD = 0.5


@reports_index_errors
def compare_takes(scene: str, slate: str | None = None, query: str | None = None) -> list[dict]:
    """Get every take of a setup, with performance and technical detail, for comparison.

    Use for "which take is best" or "which take plays angriest" style
    questions — it returns everything needed to rank takes by performance
    and to flag ones with technical problems. Pass `query` when the
    director is asking about a specific line or moment ("compare the takes
    of the line about the hand") so results are filtered to takes that
    actually contain a matching line, rather than every take of the setup.

    Args:
        scene: The scene to compare takes within, e.g. "S03".
        slate: Optionally restrict to one setup, e.g. "2A". Omit to compare
            every setup shot in the scene.
        query: Optionally, a specific line or moment to match on ("the line
            about the hand", "her angriest read"), in plain language. Takes
            without a dialogue line close enough to this description are
            dropped from the results.

    Returns:
        One row per take: slate, take number, dominant_mood, technical_notes,
        characters, its dialogue lines (with delivery and intensity), and
        the clip's timecode range. When `query` is given, dialogue is
        filtered to matching lines only.
    """
    query_vec = embed_batch([query])[0] if query else None

    where = ["c.scene = %(scene)s"]
    params: dict = {"scene": scene}
    if slate:
        where.append("c.slate = %(slate)s")
        params["slate"] = slate
    clause = " AND ".join(where)

    sql = f"""
        SELECT c.clip_id, c.scene, c.slate, c.take, c.dominant_mood,
               c.technical_notes, c.characters_present, c.summary
        FROM {config.CH_DATABASE}.clips AS c
        WHERE {clause}
        ORDER BY c.slate, c.take
    """
    result = client().query(sql, parameters=params)
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]

    ch = client()
    matched_rows = []
    for row in rows:
        if query_vec is not None:
            dlg = ch.query(
                f"""
                SELECT start_s, end_s, speaker, text, delivery, intensity,
                       cosineDistance(embedding, %(vec)s) AS distance
                FROM {config.CH_DATABASE}.dialogue
                WHERE clip_id = %(clip_id)s
                    AND cosineDistance(embedding, %(vec)s) < %(threshold)s
                ORDER BY distance ASC
                """,
                parameters={
                    "clip_id": row["clip_id"],
                    "vec": query_vec,
                    "threshold": LINE_MATCH_DISTANCE_THRESHOLD,
                },
            )
            lines = [dict(zip(dlg.column_names, line)) for line in dlg.result_rows]
            if not lines:
                continue
        else:
            dlg = ch.query(
                f"""
                SELECT start_s, end_s, speaker, text, delivery, intensity
                FROM {config.CH_DATABASE}.dialogue
                WHERE clip_id = %(clip_id)s
                ORDER BY start_s
                """,
                parameters={"clip_id": row["clip_id"]},
            )
            lines = [dict(zip(dlg.column_names, line)) for line in dlg.result_rows]
        for line in lines:
            line.pop("distance", None)
            line["timecode_in"] = timecode(line.pop("start_s"))
            line["timecode_out"] = timecode(line.pop("end_s"))
        row["dialogue"] = lines
        matched_rows.append(row)

        span = ch.query(
            f"""
            SELECT min(start_s), max(end_s)
            FROM {config.CH_DATABASE}.visuals
            WHERE clip_id = %(clip_id)s
            """,
            parameters={"clip_id": row["clip_id"]},
        )
        start_s, end_s = span.result_rows[0]
        row["timecode_in"] = timecode(start_s or 0.0)
        row["timecode_out"] = timecode(end_s or 0.0)

    logger.info(
        "compare_takes",
        extra={"scene": scene, "slate": slate, "query": query, "results": len(matched_rows)},
    )
    return matched_rows
