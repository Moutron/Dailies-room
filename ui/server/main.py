"""Between the browser and the agent."""

import math
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from ui.server.agent_runner import stream_chat
from ui.server.circle import set_circled
from ui.server.clip_list import clip_list
from ui.server.clip_meta import clip_dialogue, clip_meta, index_stats
from ui.server.clips import POSTERS_DIR, THUMBS_DIR, signed_clip_url, thumbnails
from ui.server.coverage_matrix import coverage_matrix
from ui.server.ingest import ingest_summary
from ui.server.rate_limit import allow, retry_after
from ui.server.search import browse_search
from ui.server.shot_list import list_rows, set_selected

app = FastAPI(title="Dailies Room")

# Vite's dev server (5173) proxies /chat, /clip, /thumbs, /health to this
# app (see ui/vite.config.ts), so every request is same-origin — no CORS
# middleware needed either in dev or in the production build below, where
# the built bundle is served from this same FastAPI app.


class ChatRequest(BaseModel):
    message: str
    session_id: str


@app.post("/chat")
async def chat(req: ChatRequest):
    """Stream the agent's reply, including which tools it called."""
    if not allow(req.session_id):
        wait_s = math.ceil(retry_after(req.session_id))
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a moment and try again.",
            headers={"Retry-After": str(wait_s)},
        )
    return StreamingResponse(
        stream_chat(req.message, req.session_id), media_type="text/event-stream"
    )


@app.get("/clip/{clip_id}/url")
def clip_url(clip_id: str):
    """Signed, short-lived playback URL."""
    try:
        return {"url": signed_clip_url(clip_id)}
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not sign a playback URL ({exc.__class__.__name__})."
        ) from exc


@app.get("/clip/{clip_id}/thumbnails")
def clip_thumbnails(clip_id: str):
    """Contact-strip frames for a clip: filename + timecode."""
    return {"frames": thumbnails(clip_id)}


@app.get("/clip/{clip_id}/meta")
def clip_metadata(clip_id: str):
    """Slate metadata + what Gemini saw, for the viewer panel."""
    meta = clip_meta(clip_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"No such clip: {clip_id!r}.")
    return meta


class CircleRequest(BaseModel):
    circled: bool


@app.post("/clip/{clip_id}/circle")
def circle_clip(clip_id: str, req: CircleRequest):
    """The product's first write path -- see ui/server/circle.py."""
    result = set_circled(clip_id, req.circled)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No such clip: {clip_id!r}.")
    return result


@app.get("/clip/{clip_id}/dialogue")
def clip_dialogue_lines(clip_id: str):
    """Real dialogue rows for the clip detail transcript and its dialogue-
    region overlay. A 0-line result for an indexed clip is a genuine finding
    (all three S03 clips), not an error — only a truly unindexed clip 404s."""
    lines = clip_dialogue(clip_id)
    if lines is None:
        raise HTTPException(status_code=404, detail=f"No such clip: {clip_id!r}.")
    return {"lines": lines}


@app.get("/stats")
def stats():
    """Real, countable index-wide numbers for the top bar's readout."""
    return index_stats()


@app.get("/coverage/matrix")
def coverage_matrix_route():
    """Scene/slate x shot-size grid for Screen #1c. Plain REST, not an agent
    tool -- routing a grid through the LLM is slower and less reliable for
    no benefit (see ui/server/coverage_matrix.py)."""
    return coverage_matrix()


@app.get("/shot-list/rows")
def shot_list_rows():
    """Screen #1g's rows -- generated live from the real coverage aggregate
    and upserted, never a fixture (see ui/server/shot_list.py)."""
    return {"rows": list_rows()}


class ShotListSelectRequest(BaseModel):
    selected: bool


@app.post("/shot-list/rows/{row_id}/select")
def shot_list_select(row_id: str, req: ShotListSelectRequest):
    result = set_selected(row_id, req.selected)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No such shot list row: {row_id!r}.")
    return result


@app.get("/clips")
def clips_route(
    reel: list[str] | None = Query(None),  # noqa: B008 — FastAPI's own idiom for query params
    shot_type: list[str] | None = Query(None),  # noqa: B008
):
    """Flat clip list for Screen #1d's contact sheet, filterable by reel
    and shot-type display bucket (see ui/server/clip_list.py)."""
    return {"clips": clip_list(reels=reel, shot_types=shot_type)}


@app.get("/ingest/summary")
def ingest_summary_route():
    """Screen #6's real pipeline-index state -- plain REST, static explainer
    over the same tables the rest of the app reads (see ui/server/ingest.py
    for why there is no in-flight/queued state to serve)."""
    return ingest_summary()


@app.get("/search")
def search_route(q: str, mode: str = "semantic"):
    """Screen #1d's search bar. `mode` is "semantic" (meaning-based,
    real cosineDistance) or "keyword" (ILIKE) -- see ui/server/search.py."""
    if mode not in ("semantic", "keyword"):
        raise HTTPException(status_code=400, detail="mode must be 'semantic' or 'keyword'.")
    if not q.strip():
        return {"query": q, "mode": mode, "hits": []}
    return browse_search(q, mode)


def _serve_from(root_dir: str, filename: str, not_found_detail: str) -> FileResponse:
    # filename comes straight from the URL path; a value like "../../etc/passwd"
    # (or a %2F-encoded slash smuggled through as part of the segment) must not
    # be allowed to resolve outside root_dir, so check the *resolved* path
    # rather than trusting os.path.join alone.
    root = os.path.realpath(root_dir)
    path = os.path.realpath(os.path.join(root, filename))
    if os.path.commonpath([root, path]) != root or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=not_found_detail)
    return FileResponse(path)


@app.get("/thumbs/{filename}")
def thumb_file(filename: str):
    return _serve_from(THUMBS_DIR, filename, "No such thumbnail.")


@app.get("/posters/{filename}")
def poster_file(filename: str):
    return _serve_from(POSTERS_DIR, filename, "No such poster.")


@app.get("/health")
def health():
    return {"status": "ok"}


class SPAStaticFiles(StaticFiles):
    """Serves the built SPA, falling back to index.html for unknown paths.

    React Router owns /ask, /coverage, /reels, /shot-list, /ingest, and
    /clip/{id} (see ui/src/App.tsx). Plain StaticFiles(html=True) 404s those
    on a direct load or refresh -- it only serves index.html for exact "/"
    requests, never as a catch-all. ui/vite.config.ts already solves the same
    API-route-vs-page-route collision for the dev server; this is the
    production half of it.
    """

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


_DIST = os.path.join(os.path.dirname(__file__), "..", "dist")
if os.path.isdir(_DIST):
    app.mount("/", SPAStaticFiles(directory=_DIST, html=True), name="static")
