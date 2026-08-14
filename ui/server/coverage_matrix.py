"""Coverage matrix for Screen #1c: scene/slate x shot-size -> takes, with
per-row gap status.

agent/tools/coverage.py's get_coverage answers "what coverage exists" per
clip, shaped for an LLM to reason over and shot through the character-alias
gap logic in _scene_gap_sets. The grid needs a different, purely mechanical
shape -- one row per (scene, slate), one column per shot-size bucket, filled
with the real clip_ids shot at that size -- so this is a second, plain REST
read rather than a second consumer forced through get_coverage's shape (or
worse, through the agent). It deliberately does NOT reuse get_coverage's
character-based never_appeared/unmatched_expected gap fields: this grid's
"gap" is a directly-verifiable fact readable off the row's own cells (does
any clip shot for this slate use a tight shot size), not a character-alias
inference. Two different, both-real notions of "gap" for two different
audiences.

`classification` (added for Backend 8 / ui/server/shot_list.py) is a richer
label for the same per-row gap, mapped from the mechanical cell data --
NOT from get_coverage's character-alias gap fields, for the same reason
this whole module avoids them:
  - a row with any populated tight column (MCU/CU) has no gap at all
    (`classification` is None).
  - a row whose only populated column is WIDE -> "wide coverage only":
    something was shot, just never closer than a wide.
  - a row where every clip has no visuals row joined at all (not even an
    `unknown` shot type) -> "never appeared": nothing has ever been
    visually indexed for this slate (doesn't fire on the current six-clip
    index -- every clip has a real visuals row -- but is real if it ever
    does).
  - everything else (some non-wide, non-tight coverage, e.g. MED only, or
    an unclassified `unknown` shot type) -> "coverage gap", the catch-all.
This is a considered scope decision, not pre-decided by the plan doc --
documented here because it's the one place both status and classification
are computed from the same cell data.
"""

from clickhouse_connect.driver.binding import finalize_query

from agent import config
from pipeline.ingest import client
from pipeline.schema import TIGHT_SHOT_TYPES

# shot_type is an 8-value enum (pipeline/schema.py's SHOT_TYPES); the design
# has 5 display columns. Mapping is explicit rather than derived, so a future
# enum value doesn't silently land somewhere unintended:
#   extreme_wide, wide   -> WIDE
#   medium               -> MED
#   medium_close         -> MCU
#   close, extreme_close -> CU
#   insert                -> INSERT
#   unknown               -> excluded from the 5 columns (see below).
SHOT_COLUMNS: dict[str, frozenset[str]] = {
    "WIDE": frozenset({"extreme_wide", "wide"}),
    "MED": frozenset({"medium"}),
    "MCU": frozenset({"medium_close"}),
    "CU": frozenset({"close", "extreme_close"}),
    "INSERT": frozenset({"insert"}),
}
COLUMN_ORDER: tuple[str, ...] = ("WIDE", "MED", "MCU", "CU", "INSERT")

# `unknown` isn't given its own display column -- no clip in the current
# index has ever produced it, and adding a 6th column to match an enum value
# that has never fired would make the (already sparse) real grid harder to
# read for no real benefit today. It is not silently dropped, though: any
# clip whose shot_type maps to nothing above is counted in a row's
# `unknown_clip_ids` and would surface there rather than vanish.

_SQL = f"""
    SELECT c.clip_id AS clip_id, c.scene AS scene, c.slate AS slate, c.take AS take,
           c.location AS location, c.day_night AS day_night,
           c.characters_present AS characters_present,
           v.shot_type AS shot_type,
           coalesce(dc.dialogue_count, 0) AS dialogue_count
    FROM {config.CH_DATABASE}.clips AS c
    LEFT JOIN {config.CH_DATABASE}.visuals AS v ON v.clip_id = c.clip_id
    LEFT JOIN (
        SELECT clip_id, count(*) AS dialogue_count
        FROM {config.CH_DATABASE}.dialogue
        GROUP BY clip_id
    ) AS dc ON dc.clip_id = c.clip_id
    ORDER BY c.scene, c.slate, c.take, c.clip_id
"""


def _column_for(shot_type: str | None) -> str | None:
    for column, members in SHOT_COLUMNS.items():
        if shot_type in members:
            return column
    return None


def coverage_matrix() -> dict:
    """The real grid: one row per (scene, slate), one bucket per shot-size
    column, filled with real clip_ids. Never fabricated -- a slate with no
    clip at a given size is simply an empty bucket, rendered by the frontend
    as the hatched "not shot" cell.
    """
    result = client().query(_SQL)
    clip_rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
    rendered_sql = finalize_query(_SQL, {})

    rows_by_key: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for r in clip_rows:
        key = (r["scene"], r["slate"])
        if key not in rows_by_key:
            rows_by_key[key] = {
                "scene": r["scene"],
                "slate": r["slate"],
                "take": r["take"],
                "location": r["location"],
                "day_night": r["day_night"],
                "characters": set(),
                "cells": {col: [] for col in COLUMN_ORDER},
                "unknown_clip_ids": [],
                "no_visuals_clip_ids": [],
                "dialogue_counts": [],
            }
            order.append(key)
        row = rows_by_key[key]
        row["characters"].update(r["characters_present"] or [])
        row["dialogue_counts"].append(r["dialogue_count"])
        column = _column_for(r["shot_type"])
        if column is not None:
            row["cells"][column].append(r["clip_id"])
        elif r["shot_type"] is None:
            # The LEFT JOIN found no visuals row at all for this clip --
            # distinct from a real `unknown` enum value (see
            # unknown_clip_ids below): this clip has never been visually
            # indexed, which is exactly the "never appeared" case below.
            row["no_visuals_clip_ids"].append(r["clip_id"])
        else:
            row["unknown_clip_ids"].append(r["clip_id"])

    rows: list[dict] = []
    scene_has_tight: dict[str, bool] = {}
    for key in order:
        row = rows_by_key[key]
        shot_types_present = {column for column, clip_ids in row["cells"].items() if clip_ids}
        has_tight = bool(shot_types_present & {"MCU", "CU"})
        # MCU/CU are exactly the display columns fed by TIGHT_SHOT_TYPES
        # (medium_close, close, extreme_close) -- asserted once here so the
        # two mappings can't silently drift apart.
        assert {c for c, members in SHOT_COLUMNS.items() if members & TIGHT_SHOT_TYPES} == {
            "MCU",
            "CU",
        }
        scene_has_tight[row["scene"]] = scene_has_tight.get(row["scene"], False) or has_tight

        all_no_dialogue = all(n == 0 for n in row["dialogue_counts"])
        n_chars = len(row["characters"])
        description = f"{row['location']}, {row['day_night'].title()} — {n_chars} char{'s' if n_chars != 1 else ''}"
        if all_no_dialogue:
            description += " — no dialogue"

        status = "COMPLETE" if has_tight else "NO TIGHT COVERAGE"
        if has_tight:
            classification = None
        elif shot_types_present == {"WIDE"}:
            classification = "wide coverage only"
        elif not shot_types_present and not row["unknown_clip_ids"] and row["no_visuals_clip_ids"]:
            classification = "never appeared"
        else:
            classification = "coverage gap"

        rows.append(
            {
                "scene": row["scene"],
                "slate": row["slate"],
                "take": row["take"],
                "location": row["location"],
                "day_night": row["day_night"],
                "description": description,
                "cells": row["cells"],
                "unknown_clip_ids": row["unknown_clip_ids"],
                "no_visuals_clip_ids": row["no_visuals_clip_ids"],
                "has_tight_coverage": has_tight,
                "status": status,
                "classification": classification,
            }
        )

    gap_scenes = sorted(scene for scene, tight in scene_has_tight.items() if not tight)
    scenes = sorted(scene_has_tight.keys())

    if not gap_scenes:
        headline = "Every scene has tight coverage."
    elif len(gap_scenes) == 1:
        headline = f"Scene {gap_scenes[0]} is missing tight coverage."
    else:
        headline = f"{len(gap_scenes)} scenes are missing tight coverage."

    return {
        "columns": list(COLUMN_ORDER),
        "rows": rows,
        "stats": {
            "takes_printed": len(clip_rows),
            "scenes": len(scenes),
            "gaps_flagged": sum(1 for r in rows if r["status"] != "COMPLETE"),
        },
        "gap_scenes": gap_scenes,
        "headline": headline,
        "sql": rendered_sql,
    }
