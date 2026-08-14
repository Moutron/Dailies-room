"""Circled takes -- the product's first write path.

New ReplacingMergeTree table (`schema/clickhouse.sql`'s `circled_takes`),
keyed on `clip_id` the same way `clips` already is: toggling just inserts a
new row with a fresh `updated_at`, and the highest `updated_at` per
`clip_id` wins.

ReplacingMergeTree only guarantees *eventual* deduplication -- a background
merge, or an explicit `OPTIMIZE ... FINAL` -- neither of which is
guaranteed to have happened before the next read. A plain `SELECT * FROM
circled_takes` right after two toggles can still return both rows. Every
read here resolves the winner explicitly with `argMax(circled,
updated_at)` instead of trusting the table to already be deduplicated --
this matters most for a join (clip_list.py / clip_meta.py), where an
un-merged clip_id with two rows would otherwise fan out the outer row it's
joined against.

`updated_at` is written explicitly from Python, never left to the column's
`DEFAULT now64(3)` -- confirmed live that ClickHouse Cloud's table engine
here (`SharedReplacingMergeTree`) deduplicates inserts by hashing the
*submitted* block, before server-side defaults are applied. Circling the
same clip to the same state twice (a real, common action -- circle, then
un-circle, then circle again) submits an identical `(clip_id, circled)`
tuple each time; with `updated_at` left to the default, every insert after
the first was silently dropped as a duplicate, so the write endpoint
returned 200 but the state never actually changed. Explicitly including a
real, unique `updated_at` in every submitted row makes each insert's block
distinct, which sidesteps the dedup entirely.
"""

from datetime import datetime, timezone

from agent import config
from pipeline.ingest import client

# Reused by clip_list.py and clip_meta.py so every endpoint that surfaces a
# `circled` field resolves it the same way.
CIRCLED_SUBQUERY = f"""
    SELECT clip_id, argMax(circled, updated_at) AS circled
    FROM {config.CH_DATABASE}.circled_takes
    GROUP BY clip_id
"""


def clip_exists(clip_id: str) -> bool:
    result = client().query(
        f"SELECT count(*) FROM {config.CH_DATABASE}.clips WHERE clip_id = %(clip_id)s",
        parameters={"clip_id": clip_id},
    )
    return bool(result.result_rows[0][0])


def set_circled(clip_id: str, circled: bool) -> dict | None:
    """Idempotently sets a clip's circled state. Returns None if the clip
    isn't indexed at all -- circling a clip that doesn't exist would be a
    write with no read side to ever surface it."""
    if not clip_exists(clip_id):
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    client().insert(
        "circled_takes",
        [[clip_id, int(circled), now]],
        column_names=["clip_id", "circled", "updated_at"],
    )
    return {"clip_id": clip_id, "circled": circled}
