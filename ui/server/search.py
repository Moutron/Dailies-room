"""Screen #1d's search bar: semantic and keyword, over the same two tables.

Semantic reuses `agent/tools/search.py`'s real `search_dialogue`/
`search_visuals` directly -- both already `SELECT cosineDistance(embedding,
%(vec)s) AS distance`, and `distance` survives into the returned rows
unused by the agent path. Keyword is new: an `ILIKE` path over
`dialogue.text` and `visuals.description`, since semantic search already
existed and keyword didn't (DESIGN_IMPLEMENTATION_PLAN.md's Prompt 6).

Both modes search across dialogue lines *and* visual descriptions rather
than dialogue alone, so a hit can be either kind -- `kind` distinguishes
them, since a dialogue row has a speaker/performance-note and a visual row
doesn't. Lives here, not agent/tools/, since a browse-screen search bar
is a plain REST read for a human, not something an agent tool call should
drive -- same reasoning as coverage_matrix.py and clip_list.py.
"""

from agent import config
from agent.tools.search import search_dialogue, search_visuals, timecode
from pipeline.ingest import client

_LIMIT = 6


def _similarity(distance: float) -> float:
    """cosineDistance -> a 0..1-ish similarity score for the score badge.
    Both search_dialogue/search_visuals `ORDER BY distance ASC` (lower =
    better match -- DESIGN_IMPLEMENTATION_PLAN.md's 1.6), so the score must
    move the opposite direction. Clamped at 0: a sufficiently dissimilar
    pair can return a distance > 1.
    """
    return round(max(0.0, 1.0 - distance), 2)


def _dialogue_hit(row: dict, score: float | None) -> dict:
    return {
        "kind": "dialogue",
        "clip_id": row["clip_id"],
        "scene": row.get("scene"),
        "take": row.get("take"),
        "reel": row.get("reel"),
        "timecode_in": row.get("timecode_in"),
        "quote": row["text"],
        "speaker": row.get("speaker"),
        "note": row.get("delivery") or None,
        "note_label": "performance note",
        "score": score,
    }


def _visual_hit(row: dict, score: float | None) -> dict:
    return {
        "kind": "visual",
        "clip_id": row["clip_id"],
        "scene": row.get("scene"),
        "take": row.get("take"),
        "reel": row.get("reel"),
        "timecode_in": row.get("timecode_in"),
        "quote": row["description"],
        "speaker": None,
        "note": row.get("camera_movement") or None,
        "note_label": "camera movement",
        "score": score,
    }


def _semantic_search(query: str) -> list[dict]:
    dialogue_rows = search_dialogue(query, limit=_LIMIT)
    visual_rows = search_visuals(query, limit=_LIMIT)
    hits = [_dialogue_hit(r, _similarity(r["distance"])) for r in dialogue_rows if "error" not in r]
    hits += [_visual_hit(r, _similarity(r["distance"])) for r in visual_rows if "error" not in r]
    hits.sort(key=lambda h: -h["score"])
    return hits[:_LIMIT]


def _keyword_hits_dialogue(pattern: str) -> list[dict]:
    sql = f"""
        SELECT clip_id AS clip_id, scene AS scene, take AS take, start_s AS start_s,
               speaker AS speaker, text AS text, delivery AS delivery,
               reel AS reel, tc_start_s AS tc_start_s
        FROM {config.CH_DATABASE}.dialogue
        WHERE text ILIKE %(pattern)s
        ORDER BY start_s
        LIMIT %(limit)s
    """
    result = client().query(sql, parameters={"pattern": pattern, "limit": _LIMIT})
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
    hits = []
    for r in rows:
        offset = r.pop("tc_start_s")
        r["timecode_in"] = timecode(r.pop("start_s"), offset)
        hits.append(_dialogue_hit(r, None))
    return hits


def _keyword_hits_visual(pattern: str) -> list[dict]:
    sql = f"""
        SELECT clip_id AS clip_id, scene AS scene, take AS take, start_s AS start_s,
               description AS description, camera_movement AS camera_movement,
               reel AS reel, tc_start_s AS tc_start_s
        FROM {config.CH_DATABASE}.visuals
        WHERE description ILIKE %(pattern)s
        ORDER BY start_s
        LIMIT %(limit)s
    """
    result = client().query(sql, parameters={"pattern": pattern, "limit": _LIMIT})
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
    hits = []
    for r in rows:
        offset = r.pop("tc_start_s")
        r["timecode_in"] = timecode(r.pop("start_s"), offset)
        hits.append(_visual_hit(r, None))
    return hits


def _keyword_search(query: str) -> list[dict]:
    pattern = f"%{query}%"
    hits = _keyword_hits_dialogue(pattern) + _keyword_hits_visual(pattern)
    return hits[:_LIMIT]


def browse_search(query: str, mode: str) -> dict:
    """Real search results for Screen #1d's search bar. `mode` is
    "semantic" (meaning-based, cosineDistance -- score badge shown) or
    "keyword" (ILIKE -- no score, since nothing in a substring match is
    actually ranked; the UI must not show a badge for these rows)."""
    hits = _semantic_search(query) if mode == "semantic" else _keyword_search(query)
    return {"query": query, "mode": mode, "hits": hits}
