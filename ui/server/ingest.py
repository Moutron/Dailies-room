"""Screen #6/#1f's static explainer: real per-clip state and index-wide
counts for the ingest pipeline strip.

No job runner, status table, or polling endpoint exists -- pipeline/ingest.py
is an offline batch script with no notion of "in flight" (see
DESIGN_IMPLEMENTATION_PLAN.md's Prompt 8 notes). Every clip currently in the
index has already finished the same four stages, so this reads the same
`clips`/`dialogue` tables the rest of the app already reads rather than
fabricating an in-flight or queued row -- there is nothing in this schema
that could honestly produce one.
"""

from agent import config
from pipeline.ingest import client
from ui.server.clip_meta import index_stats

# Same pre-aggregated-subquery dialogue_count pattern as clip_meta.py's
# clip_meta() and coverage_matrix.py's coverage_matrix() -- ClickHouse
# doesn't support correlated subqueries, so the per-clip count comes from a
# LEFT JOIN against a GROUP BY subquery rather than a fourth ad hoc version
# of the same query.
_SQL = f"""
    SELECT c.clip_id AS clip_id, c.duration_s AS duration_s,
           c.ingested_at AS ingested_at,
           coalesce(dc.dialogue_count, 0) AS dialogue_count
    FROM {config.CH_DATABASE}.clips AS c
    LEFT JOIN (
        SELECT clip_id, count(*) AS dialogue_count
        FROM {config.CH_DATABASE}.dialogue
        GROUP BY clip_id
    ) AS dc ON dc.clip_id = c.clip_id
    ORDER BY c.ingested_at DESC, c.clip_id
"""


def _embeddings_count() -> int:
    """Every dialogue/visuals row carries one embedding vector written at
    ingest (schema/clickhouse.sql) -- a real, countable total, not the
    mockup's fabricated 418."""
    dialogue = (
        client().query(f"SELECT count(*) FROM {config.CH_DATABASE}.dialogue").result_rows[0][0]
    )
    visuals = client().query(f"SELECT count(*) FROM {config.CH_DATABASE}.visuals").result_rows[0][0]
    return dialogue + visuals


def ingest_summary() -> dict:
    """Real state of the whole index for Screen #6. Every clip is uniformly
    READY -- there is no in-flight or queued state to render honestly, so
    none is synthesized here. `most_recent_ingested_at` replaces the
    mockup's fake "N CLIPS IN FLIGHT" live badge with a real timestamp.
    AVG PER CLIP is omitted entirely: per-clip ingest duration is recorded
    nowhere in this schema."""
    result = client().query(_SQL)
    clips = [dict(zip(result.column_names, row)) for row in result.result_rows]
    for c in clips:
        c["state"] = "READY"

    stats = index_stats()
    return {
        "clips": clips,
        "indexed_today": stats["clip_count"],
        "embeddings": _embeddings_count(),
        "most_recent_ingested_at": clips[0]["ingested_at"] if clips else None,
    }
