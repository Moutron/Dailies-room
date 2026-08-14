"""Shot list -- flagged coverage gaps turned into pickups, screen #1g.

New ReplacingMergeTree table (`schema/clickhouse.sql`'s `shot_list`), keyed
on `row_id`, the same idempotent-upsert pattern `clips` and `circled_takes`
already use. Rows are never authored by hand: `generate_rows()` derives
them live from `ui/server/coverage_matrix.py`'s real per-row
`classification` (the gap-mapping documented there) every time the shot
list is read, and `list_rows()` upserts them -- so the explainer copy's
claim that "each row came from an aggregate" is literally true at write
time, not just at first load, and never from a fixture.

`row_id` is deterministic (`scene-slate`), so re-generating always lands
in the same slot and a user's `selected` toggle survives a later
regeneration, as long as the underlying gap is still real. `qualifier`
(the location/day_night line beside the title) is derived data too --
it's returned in the API response but deliberately not one of Backend 8's
persisted columns, since it's cheap to recompute from the live aggregate
on every read and storing it would just be a second, staler copy.

`created_at` is always written explicitly from Python, never left to the
column's `DEFAULT now64(3)` -- same fix as `circle.py`'s `updated_at`, for
the same confirmed-live reason: this table's engine (ClickHouse Cloud's
`SharedReplacingMergeTree`) deduplicates inserts by hashing the submitted
block, before server-side defaults are applied, so re-selecting a row back
to a value it already held (a real, common action) submitted an identical
tuple and was silently dropped -- see `_now()`.
"""

from datetime import datetime, timezone

from agent import config
from pipeline.ingest import client
from ui.server.coverage_matrix import coverage_matrix


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_SELECTED_SUBQUERY = f"""
    SELECT row_id, argMax(selected, created_at) AS selected
    FROM {config.CH_DATABASE}.shot_list
    GROUP BY row_id
"""

_REASON_BY_CLASSIFICATION = {
    "wide coverage only": "Only wide coverage exists for this slate — no medium or tighter take was shot.",
    "never appeared": "No visual coverage is indexed for this slate at all.",
}


def _row_id(scene: str, slate: str) -> str:
    return f"{scene}-{slate}"


def _qualifier(row: dict) -> str:
    return f"{row['location'].lower()}, {row['day_night'].lower()}"


def _reason(row: dict) -> str:
    fixed = _REASON_BY_CLASSIFICATION.get(row["classification"])
    if fixed:
        return fixed
    # "coverage gap": name whatever real, non-tight shot sizes do exist.
    populated = [c for c in ("WIDE", "MED", "MCU", "CU", "INSERT") if row["cells"].get(c)]
    n = sum(len(ids) for ids in row["cells"].values()) + len(row["unknown_clip_ids"])
    cols = ", ".join(populated) if populated else "no classified shot type"
    return f"Nothing tighter than {cols} exists across the {n} take{'s' if n != 1 else ''} for this slate."


def _source_clip(row: dict) -> str:
    ids = sorted(
        {cid for ids in row["cells"].values() for cid in ids}
        | set(row["unknown_clip_ids"])
        | set(row["no_visuals_clip_ids"])
    )
    return ids[0] if ids else ""


def generate_rows() -> list[dict]:
    """The real gap rows out of the live coverage aggregate -- one per
    (scene, slate) whose classification isn't None (see
    coverage_matrix.py's docstring for the classification mapping)."""
    matrix = coverage_matrix()
    return [
        {
            "row_id": _row_id(row["scene"], row["slate"]),
            "title": f"{row['scene']} · {row['slate']}",
            "qualifier": _qualifier(row),
            "reason": _reason(row),
            "source_clip": _source_clip(row),
            "classification": row["classification"],
        }
        for row in matrix["rows"]
        if row["classification"] is not None
    ]


def _selected_by_row_id() -> dict[str, bool]:
    result = client().query(_SELECTED_SUBQUERY)
    return {row_id: bool(selected) for row_id, selected in result.result_rows}


def list_rows() -> list[dict]:
    """Regenerates the shot list from the live coverage aggregate, upserts
    any new/changed row (preserving each row's persisted `selected` value),
    and returns the merged current state."""
    generated = generate_rows()
    existing_selected = _selected_by_row_id()

    insert_rows = [
        [
            row["row_id"],
            row["title"],
            row["reason"],
            row["source_clip"],
            row["classification"],
            int(existing_selected.get(row["row_id"], False)),
            _now(),
        ]
        for row in generated
    ]
    if insert_rows:
        client().insert(
            "shot_list",
            insert_rows,
            column_names=[
                "row_id",
                "title",
                "reason",
                "source_clip",
                "classification",
                "selected",
                "created_at",
            ],
        )

    return [{**row, "selected": existing_selected.get(row["row_id"], False)} for row in generated]


def set_selected(row_id: str, selected: bool) -> dict | None:
    """Toggles one row's checkbox. Returns None if row_id isn't a row the
    current generation cycle produced -- selecting a gap that no longer
    exists would be a write with no read side to ever surface it."""
    generated = {row["row_id"]: row for row in generate_rows()}
    row = generated.get(row_id)
    if row is None:
        return None
    client().insert(
        "shot_list",
        [
            [
                row["row_id"],
                row["title"],
                row["reason"],
                row["source_clip"],
                row["classification"],
                int(selected),
                _now(),
            ]
        ],
        column_names=[
            "row_id",
            "title",
            "reason",
            "source_clip",
            "classification",
            "selected",
            "created_at",
        ],
    )
    return {**row, "selected": selected}
