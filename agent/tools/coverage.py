"""Coverage over a scene: what setups exist and what each one shows."""

import functools
import json
import logging
from pathlib import Path

from agent import config
from agent.tools._errors import reports_index_errors
from agent.tools.search import timecode
from pipeline.ingest import client
from pipeline.schema import TIGHT_SHOT_TYPES

logger = logging.getLogger(__name__)

_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "manifest.json"


@functools.lru_cache
def _character_aliases() -> dict[str, frozenset[str]]:
    """Call-sheet name -> every name Gemini has actually used for that person.

    Gemini names on-screen characters per clip from what it sees on screen,
    not from a call sheet, so the same actor becomes "ACTOR_SITTING_WITH_RIFLE"
    in one clip and "UNKNOWN_MAN" in the next. Without resolving through this
    map first, `characters_expected - characters_present` reports someone as
    never shot when they're in every clip — a tool asserting a falsehood the
    honesty prompt can't catch, because the model is correctly relaying what
    the tool told it.
    """
    data = json.loads(_MANIFEST_PATH.read_text())
    return {
        canonical: frozenset({canonical, *aka})
        for canonical, aka in data.get("character_aliases", {}).items()
    }


def _known_scenes() -> list[str]:
    """Every scene identifier actually present in the index."""
    sql = f"SELECT DISTINCT scene FROM {config.CH_DATABASE}.clips ORDER BY scene"
    return [row[0] for row in client().query(sql).result_rows]


def _scene_gap_sets(scene: str) -> dict[str, list[str]]:
    """Character sets for gap analysis, aggregated across the whole scene in SQL.

    Previously these were accumulated in Python by iterating the listing
    query's rows — which meant gap correctness was coupled to however that
    query happened to fan out per clip (it's grouped by shot_type/
    camera_movement, so a clip with visual segments of different shot types
    produces more than one row for it). `groupUniqArrayArray` flattens+dedupes
    the Array(String) columns server-side, and `has()` picks out only the
    tight-shot characters, independent of how many rows the listing query
    below returns for any given clip.
    """
    sql = f"""
        SELECT
            groupUniqArrayArray(c.characters_expected) AS expected,
            groupUniqArrayArray(c.characters_present) AS present,
            groupUniqArrayArray(v.characters_visible) AS any_shot_chars,
            groupUniqArrayArray(
                if(has(%(tight_types)s, lower(toString(v.shot_type))), v.characters_visible, [])
            ) AS tight_shot_chars
        FROM {config.CH_DATABASE}.clips AS c
        LEFT JOIN {config.CH_DATABASE}.visuals AS v ON v.clip_id = c.clip_id
        WHERE c.scene = %(scene)s
    """
    result = client().query(sql, parameters={"scene": scene, "tight_types": list(TIGHT_SHOT_TYPES)})
    return dict(zip(result.column_names, result.result_rows[0]))


@reports_index_errors
def get_coverage(scene: str | None = None) -> list[dict]:
    """List the setups (slates) shot for a scene, with shot type, content, and gaps.

    Use for "what coverage do we have" or "are we missing anything" style
    questions — it answers by setup, not by individual line or shot, so
    pair it with search_dialogue or search_visuals when the director wants
    a specific moment.

    Args:
        scene: Restrict to one scene, e.g. "S03". Must be a scene identifier,
            not a description — "the bridge scene" is not a valid value; use
            search_visuals/search_dialogue to resolve a description to its
            scene first. Omit to list every scene (a valid way to see what
            scenes exist).

    Returns:
        One row per clip in the common case — but shot_type/camera_movement
        come from the clip's visual segment(s), and are part of the query's
        GROUP BY, so a clip with more than one visual segment whose shot_type
        or camera_movement differ will produce more than one row for that
        clip. (Every clip ingested so far has exactly one visual segment, so
        this hasn't been hit in practice, but it isn't enforced.) When
        `scene` is given, also includes scene-level gap fields — computed by
        a separate SQL aggregate query (`_scene_gap_sets`), not derived from
        these listed rows, so they're correct regardless of how the listing
        rows fan out: `never_appeared` (characters expected in the scene,
        resolved through the character alias map, but present in no clip
        under any of their known names), `unmatched_expected` (characters
        expected but not resolvable to any name Gemini detected — report
        these as an inability to match, not as confirmed absence),
        `no_tight_shot` (characters with coverage but never in a close/tight
        shot), and `wide_coverage` (characters who only ever appear in wide
        shots).
    """
    where = "WHERE c.scene = %(scene)s" if scene else ""
    params: dict = {"scene": scene} if scene else {}

    sql = f"""
        SELECT c.clip_id, c.scene, c.slate, c.take, c.location, c.day_night,
               c.summary, c.characters_present, c.characters_expected,
               c.technical_notes, c.reel, c.tc_start_s,
               v.shot_type, v.camera_movement,
               min(v.start_s) AS start_s, max(v.end_s) AS end_s
        FROM {config.CH_DATABASE}.clips AS c
        LEFT JOIN {config.CH_DATABASE}.visuals AS v ON v.clip_id = c.clip_id
        {where}
        GROUP BY c.clip_id, c.scene, c.slate, c.take, c.location, c.day_night,
                 c.summary, c.characters_present, c.characters_expected,
                 c.technical_notes, c.reel, c.tc_start_s, v.shot_type,
                 v.camera_movement
        ORDER BY c.scene, c.slate, c.take
    """
    result = client().query(sql, parameters=params)
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]

    if scene and not rows:
        # An unrecognized scene identifier and a scene with no footage are
        # indistinguishable from an empty result set — and the model, asked
        # about "the bridge scene", will sometimes pass that phrase straight
        # through as `scene`. Returning [] then reads as a confirmed negative
        # ("no coverage exists"), which is exactly the false assertion the
        # honesty prompt can't catch, because the tool told it so. Every
        # ingested scene has clips by construction, so no rows here means the
        # identifier didn't match: say so, and hand back the real scene list
        # so the model can retry rather than guess.
        return [
            {
                "error": (
                    f"No scene matching {scene!r}. `scene` must be a scene "
                    f"identifier, not a description — resolve descriptions "
                    f"like 'the bridge scene' with search_visuals or "
                    f"search_dialogue first, then call get_coverage with the "
                    f"scene it reports."
                ),
                "error_type": "unknown_scene",
                "known_scenes": _known_scenes(),
            }
        ]

    if scene and rows:
        gap_sets = _scene_gap_sets(scene)
        expected: set[str] = set(gap_sets["expected"])
        present: set[str] = set(gap_sets["present"])
        any_shot_chars: set[str] = set(gap_sets["any_shot_chars"])
        tight_shot_chars: set[str] = set(gap_sets["tight_shot_chars"])

        aliases = _character_aliases()
        never_appeared: list[str] = []
        unmatched_expected: list[str] = []
        for name in sorted(expected):
            aka = aliases.get(name)
            if aka is None:
                # No alias entry for this name at all — we have no way to
                # know what Gemini would have called them, so absence is not
                # provable. Report it as unmatched, never as a bare negative.
                unmatched_expected.append(name)
            elif not (aka & present):
                never_appeared.append(name)

        gaps = {
            "never_appeared": never_appeared,
            "unmatched_expected": unmatched_expected,
            "no_tight_shot": sorted(present - tight_shot_chars),
            "wide_coverage": sorted(any_shot_chars - tight_shot_chars),
        }
        for row in rows:
            offset = row.pop("tc_start_s")
            row["timecode_in"] = timecode(row.pop("start_s"), offset)
            row["timecode_out"] = timecode(row.pop("end_s"), offset)
        rows[0] = {**rows[0], **gaps}
        logger.info("get_coverage", extra={"scene": scene, "results": len(rows)})
        return rows

    for row in rows:
        offset = row.pop("tc_start_s")
        row["timecode_in"] = timecode(row.pop("start_s"), offset)
        row["timecode_out"] = timecode(row.pop("end_s"), offset)
    logger.info("get_coverage", extra={"scene": scene, "results": len(rows)})
    return rows
