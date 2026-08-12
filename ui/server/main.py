"""Between the browser and the agent."""

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ui.server.agent_runner import stream_chat
from ui.server.clips import THUMBS_DIR, signed_clip_url, thumbnails

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


@app.get("/thumbs/{filename}")
def thumb_file(filename: str):
    path = os.path.join(THUMBS_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="No such thumbnail.")
    return FileResponse(path)


@app.get("/health")
def health():
    return {"status": "ok"}


_DIST = os.path.join(os.path.dirname(__file__), "..", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")
