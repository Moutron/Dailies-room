"""Flat clip list for Screen #1d's contact sheet and rail filters.

Reuses `ui/server/coverage_matrix.py`'s `SHOT_COLUMNS` mapping for the
shot-type filter vocabulary (WIDE/MED/MCU/CU/INSERT) rather than
re-deriving the 8-value enum -> 5-column mapping a third time. Real `take` is not a
unique per-clip label -- all three S01 clips share scene=S01/slate=1A/
take=1 (different performances of the same setup, not different takes; see
schema/clickhouse.sql's comment on `clips` and coverage_matrix.py's
docstring) -- so callers key and display by `clip_id`, never assume
`(scene, slate, take)` is unique.

Poster URLs are deliberately not part of this payload: `getPosterUrl(clipId)`
(ui/src/api.ts) already builds the URL client-side from a deterministic
filename, so returning one here would just be a second, redundant way to
compute the same string.
"""

from agent import config
from pipeline.ingest import client
from ui.server.circle import CIRCLED_SUBQUERY
from ui.server.coverage_matrix import SHOT_COLUMNS

_SQL = f"""
    SELECT c.clip_id AS clip_id, c.reel AS reel, c.scene AS scene, c.slate AS slate,
           c.take AS take, c.duration_s AS duration_s,
           v.shot_type AS shot_type,
           coalesce(ct.circled, 0) AS circled
    FROM {config.CH_DATABASE}.clips AS c
    LEFT JOIN {config.CH_DATABASE}.visuals AS v ON v.clip_id = c.clip_id
    LEFT JOIN ({CIRCLED_SUBQUERY}) AS ct ON ct.clip_id = c.clip_id
    ORDER BY c.reel, c.clip_id
"""


def clip_list(reels: list[str] | None = None, shot_types: list[str] | None = None) -> list[dict]:
    """All indexed clips, optionally filtered by reel (exact match against
    the real `clips.reel` value) and/or shot-type display bucket (the
    design's WIDE/MED/MCU/CU/INSERT columns, not the raw 8-value enum).
    Both filters are additive within themselves (reel=A002&reel=A007 is an
    OR) and ANDed against each other, matching the rail's checkbox UI.
    """
    result = client().query(_SQL)
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
    for r in rows:
        r["circled"] = bool(r["circled"])

    if reels:
        wanted_reels = set(reels)
        rows = [r for r in rows if r["reel"] in wanted_reels]

    if shot_types:
        wanted_raw: set[str] = set()
        for bucket in shot_types:
            wanted_raw |= SHOT_COLUMNS.get(bucket, frozenset())
        rows = [r for r in rows if r["shot_type"] in wanted_raw]

    return rows
