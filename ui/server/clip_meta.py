"""Real clip metadata and index-wide stats for the UI chrome.

Screen #1a's viewer needs the slate block (scene/slate/take/duration/camera)
and "what Gemini saw" (description + notable elements) for whatever clip is
loaded, and the top bar's "N CLIPS INDEXED · TRT" readout needs a real count
and total duration — none of that is agent-tool shaped (it's not a search,
there's nothing for a model to reason about), so it's plain ClickHouse reads
here rather than a tool agent/tools/ would expose.
"""

from agent import config
from pipeline.ingest import client
from ui.server.circle import CIRCLED_SUBQUERY


def clip_meta(clip_id: str) -> dict | None:
    """Everything the viewer needs for one clip, or None if it isn't indexed.

    LIMIT 1 on the visuals join: every clip ingested so far has exactly one
    visual segment (see agent/tools/coverage.py's docstring for the same
    caveat) — not enforced by the schema, just true of the current index.
    """
    # ClickHouse doesn't support correlated subqueries (a subquery referring
    # to the outer query's alias silently returns NULL instead of erroring —
    # confirmed against the live cluster), so the per-clip dialogue count
    # comes from a LEFT JOIN against a pre-aggregated subquery instead of
    # `(SELECT count(*) ... WHERE d.clip_id = c.clip_id)`.
    #
    # Every SELECTed column is explicitly aliased: `visuals` and this
    # dialogue subquery both carry columns also named clip_id/scene/take/reel
    # (denormalized from `clips`), and past two joined tables ClickHouse
    # starts qualifying the *unaliased* output names with their table prefix
    # ("c.clip_id" instead of "clip_id") even for columns that aren't
    # actually selected ambiguously — confirmed by testing directly against
    # the live cluster. Explicit aliases sidestep that instead of relying on
    # ClickHouse's naming heuristic.
    sql = f"""
        SELECT c.clip_id AS clip_id, c.scene AS scene, c.slate AS slate, c.take AS take,
               c.location AS location, c.day_night AS day_night,
               c.duration_s AS duration_s, c.reel AS reel, c.ingested_at AS ingested_at,
               c.tc_start_s AS tc_start_s,
               v.shot_type AS shot_type, v.camera_movement AS camera_movement,
               v.description AS description, v.notable_elements AS notable_elements,
               coalesce(dc.dialogue_count, 0) AS dialogue_count,
               coalesce(ct.circled, 0) AS circled
        FROM {config.CH_DATABASE}.clips AS c
        LEFT JOIN {config.CH_DATABASE}.visuals AS v ON v.clip_id = c.clip_id
        LEFT JOIN (
            SELECT clip_id, count(*) AS dialogue_count
            FROM {config.CH_DATABASE}.dialogue
            GROUP BY clip_id
        ) AS dc ON dc.clip_id = c.clip_id
        LEFT JOIN ({CIRCLED_SUBQUERY}) AS ct ON ct.clip_id = c.clip_id
        WHERE c.clip_id = %(clip_id)s
        ORDER BY v.start_s
        LIMIT 1
    """
    result = client().query(sql, parameters={"clip_id": clip_id})
    if not result.result_rows:
        return None
    meta = dict(zip(result.column_names, result.result_rows[0]))
    meta["circled"] = bool(meta["circled"])
    return meta


def clip_dialogue(clip_id: str) -> list[dict] | None:
    """Real dialogue rows for one clip, in playback order — clip detail's
    transcript panel and its dialogue-region overlay both read this
    directly rather than reinventing the shape `ResultRow.dialogue` already
    carries elsewhere.

    Returns None (not an empty list) when the clip itself isn't indexed, so
    the caller can tell "no such clip" (404) apart from "indexed clip with
    zero dialogue lines" (a real, expected state for all three S03 clips).
    """
    exists = client().query(
        f"SELECT count(*) FROM {config.CH_DATABASE}.clips WHERE clip_id = %(clip_id)s",
        parameters={"clip_id": clip_id},
    )
    if not exists.result_rows[0][0]:
        return None

    sql = f"""
        SELECT segment_idx AS segment_idx, start_s AS start_s, end_s AS end_s,
               speaker AS speaker, text AS text, delivery AS delivery
        FROM {config.CH_DATABASE}.dialogue
        WHERE clip_id = %(clip_id)s
        ORDER BY start_s
    """
    result = client().query(sql, parameters={"clip_id": clip_id})
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


def index_stats() -> dict:
    """Real, countable numbers for the top bar's readout — never a demo number."""
    sql = f"SELECT count(*) AS clip_count, sum(duration_s) AS total_duration_s FROM {config.CH_DATABASE}.clips"
    result = client().query(sql)
    clip_count, total_duration_s = result.result_rows[0]
    return {"clip_count": clip_count, "total_duration_s": total_duration_s or 0.0}
