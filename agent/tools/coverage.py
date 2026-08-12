"""Coverage over a scene: what setups exist and what each one shows."""

import logging

from agent import config
from agent.tools._errors import reports_index_errors
from agent.tools.search import timecode
from pipeline.ingest import client

logger = logging.getLogger(__name__)

TIGHT_SHOT_TYPES = {"close", "close-up", "closeup", "tight", "extreme close-up", "ecu"}


@reports_index_errors
def get_coverage(scene: str | None = None) -> list[dict]:
    """List the setups (slates) shot for a scene, with shot type, content, and gaps.

    Use for "what coverage do we have" or "are we missing anything" style
    questions — it answers by setup, not by individual line or shot, so
    pair it with search_dialogue or search_visuals when the director wants
    a specific moment.

    Args:
        scene: Restrict to one scene, e.g. "S03". Omit to list every scene.

    Returns:
        One row per clip: scene, slate, take, shot_type, characters,
        summary, technical_notes, and the clip's timecode range. When
        `scene` is given, also includes scene-level gap fields:
        `never_appeared` (characters expected in the scene but present in
        no clip), `no_tight_shot` (characters with coverage but never in a
        close/tight shot), and `wide_coverage` (characters who only ever
        appear in wide shots).
    """
    where = "WHERE c.scene = %(scene)s" if scene else ""
    params: dict = {"scene": scene} if scene else {}

    sql = f"""
        SELECT c.clip_id, c.scene, c.slate, c.take, c.location, c.day_night,
               c.summary, c.characters_present, c.characters_expected,
               c.technical_notes,
               v.shot_type, v.camera_movement, v.characters_visible,
               min(v.start_s) AS start_s, max(v.end_s) AS end_s
        FROM {config.CH_DATABASE}.clips AS c
        LEFT JOIN {config.CH_DATABASE}.visuals AS v ON v.clip_id = c.clip_id
        {where}
        GROUP BY c.clip_id, c.scene, c.slate, c.take, c.location, c.day_night,
                 c.summary, c.characters_present, c.characters_expected,
                 c.technical_notes, v.shot_type, v.camera_movement,
                 v.characters_visible
        ORDER BY c.scene, c.slate, c.take
    """
    result = client().query(sql, parameters=params)
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]

    if scene and rows:
        expected: set[str] = set()
        present: set[str] = set()
        for row in rows:
            expected.update(row["characters_expected"] or [])
            present.update(row["characters_present"] or [])

        tight_shot_chars: set[str] = set()
        any_shot_chars: set[str] = set()
        for row in rows:
            chars_visible = row["characters_visible"] or []
            any_shot_chars.update(chars_visible)
            if (row["shot_type"] or "").strip().lower() in TIGHT_SHOT_TYPES:
                tight_shot_chars.update(chars_visible)

        gaps = {
            "never_appeared": sorted(expected - present),
            "no_tight_shot": sorted(present - tight_shot_chars),
            "wide_coverage": sorted(any_shot_chars - tight_shot_chars),
        }
        for row in rows:
            row.pop("characters_visible", None)
            row["timecode_in"] = timecode(row.pop("start_s"))
            row["timecode_out"] = timecode(row.pop("end_s"))
        rows[0] = {**rows[0], **gaps}
        logger.info("get_coverage", extra={"scene": scene, "results": len(rows)})
        return rows

    for row in rows:
        row.pop("characters_visible", None)
        row["timecode_in"] = timecode(row.pop("start_s"))
        row["timecode_out"] = timecode(row.pop("end_s"))
    logger.info("get_coverage", extra={"scene": scene, "results": len(rows)})
    return rows
