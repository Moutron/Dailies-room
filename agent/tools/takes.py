"""Compare takes of the same setup."""

import logging

from agent import config
from agent.tools._errors import reports_index_errors
from agent.tools.search import timecode
from pipeline.embed import embed_batch
from pipeline.ingest import client

logger = logging.getLogger(__name__)

# Untuned: chosen by inspection, not validated against real repeated-line
# data. S01 has real dialogue now, but each line only occurs once (a
# theatrical cut, not alternate takes of an identical read) — there's still
# no ingested case of the same line delivered two different ways to tune
# this against.
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

    # One round trip for every take of the setup, not one per take (the old
    # code ran a dialogue query and a visuals-span query per clip row — 2N+1
    # ClickHouse round trips for N takes). groupArray(tuple(...)) pulls each
    # clip's dialogue lines back as a single nested column instead.
    #
    # When `query` filters by line, the dialogue subquery is an INNER JOIN:
    # a clip with zero lines under the distance threshold contributes no
    # group at all, so it's dropped from the result the same way the old
    # `if not lines: continue` dropped it — just done by the join instead of
    # a Python loop.
    if query_vec is not None:
        params["vec"] = query_vec
        params["threshold"] = LINE_MATCH_DISTANCE_THRESHOLD
        dialogue_cols = ["start_s", "end_s", "speaker", "text", "delivery", "intensity", "distance"]
        dialogue_select = f"""
            SELECT clip_id, start_s, end_s, speaker, text, delivery, intensity,
                   cosineDistance(embedding, %(vec)s) AS distance
            FROM {config.CH_DATABASE}.dialogue
            WHERE clip_id IN (SELECT clip_id FROM matched_clips)
                AND cosineDistance(embedding, %(vec)s) < %(threshold)s
            ORDER BY clip_id, distance ASC
        """
        dialogue_join = "INNER JOIN"
    else:
        dialogue_cols = ["start_s", "end_s", "speaker", "text", "delivery", "intensity"]
        dialogue_select = f"""
            SELECT clip_id, start_s, end_s, speaker, text, delivery, intensity
            FROM {config.CH_DATABASE}.dialogue
            WHERE clip_id IN (SELECT clip_id FROM matched_clips)
            ORDER BY clip_id, start_s
        """
        dialogue_join = "LEFT JOIN"

    sql = f"""
        WITH matched_clips AS (
            SELECT c.clip_id, c.scene, c.slate, c.take, c.dominant_mood,
                   c.technical_notes, c.characters_present, c.summary,
                   c.reel, c.tc_start_s
            FROM {config.CH_DATABASE}.clips AS c
            WHERE {clause}
        )
        SELECT mc.clip_id AS clip_id, mc.scene, mc.slate, mc.take, mc.dominant_mood,
               mc.technical_notes, mc.characters_present, mc.summary,
               mc.reel, mc.tc_start_s,
               dlg.lines AS dialogue_lines,
               vis.start_s AS vis_start_s, vis.end_s AS vis_end_s
        FROM matched_clips AS mc
        {dialogue_join} (
            SELECT clip_id, groupArray(({", ".join(dialogue_cols)})) AS lines
            FROM ({dialogue_select})
            GROUP BY clip_id
        ) AS dlg ON dlg.clip_id = mc.clip_id
        LEFT JOIN (
            SELECT clip_id, min(start_s) AS start_s, max(end_s) AS end_s
            FROM {config.CH_DATABASE}.visuals
            WHERE clip_id IN (SELECT clip_id FROM matched_clips)
            GROUP BY clip_id
        ) AS vis ON vis.clip_id = mc.clip_id
        ORDER BY mc.slate, mc.take
    """
    result = client().query(sql, parameters=params)
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]

    matched_rows = []
    for row in rows:
        offset = row.pop("tc_start_s")
        lines = [dict(zip(dialogue_cols, line)) for line in (row.pop("dialogue_lines") or [])]
        for line in lines:
            line.pop("distance", None)
            line["timecode_in"] = timecode(line.pop("start_s"), offset)
            line["timecode_out"] = timecode(line.pop("end_s"), offset)
        row["dialogue"] = lines

        start_s = row.pop("vis_start_s") or 0.0
        end_s = row.pop("vis_end_s") or 0.0
        row["timecode_in"] = timecode(start_s, offset)
        row["timecode_out"] = timecode(end_s, offset)
        matched_rows.append(row)

    logger.info(
        "compare_takes",
        extra={"scene": scene, "slate": slate, "query": query, "results": len(matched_rows)},
    )
    return matched_rows
