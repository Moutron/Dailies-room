"""POST /ingest/upload -- runs an uploaded clip through the real pipeline,
synchronously, until it is searchable in Ask/Reels.

One request, no job runner: upload -> GCS -> Gemini -> embed -> ClickHouse.
Kept public (see docs/SECURITY.md) behind its own, stricter rate-limit
bucket (ui/server/rate_limit.py) -- an upload costs a Gemini video call plus
an embed call, far more than a /chat turn.
"""

import math
import re
import tempfile
from pathlib import Path

from fastapi import File, Form, HTTPException, UploadFile

from agent import config
from pipeline.encode import DEFAULT_FPS, EncodeError, frames_to_mp4
from pipeline.ingest import _probe_duration, build_rows, insert_rows
from pipeline.posters import _extract_poster_from
from pipeline.understand import analyse_clip
from ui.server.clips import delete_blob, upload_blob
from ui.server.ingest import clip_summary_row
from ui.server.rate_limit import allow, retry_after

# Shared with ui/server/main.py's poster GCS-fallback filename check, so a
# GCS blob name can never be built from something that wasn't validated as
# an actual clip_id shape.
CLIP_ID_PATTERN = r"[a-z0-9_]{1,64}"
CLIP_ID_RE = re.compile(rf"^{CLIP_ID_PATTERN}$")

# Cloud Run caps HTTP/1 request bodies at 32 MiB; lifting this means
# switching to a signed resumable upload straight to GCS, not raising this
# constant -- a synchronous FastAPI UploadFile read still has to fit in one
# request either way.
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
MAX_FRAMES = 300
ALLOWED_FRAME_EXTS = {".jpg", ".jpeg", ".png"}
ALLOWED_FRAME_CONTENT_TYPES = {"image/jpeg", "image/png"}
ALLOWED_MP4_CONTENT_TYPES = {"video/mp4"}

# Uploads are rate-limited far more tightly than /chat (CAPACITY=5,
# REFILL_SECONDS=3.0, ui/server/rate_limit.py) because each one costs a real
# Gemini video-analysis call plus an embed call, not just a chat turn.
UPLOAD_RATE_NAMESPACE = "upload"
UPLOAD_RATE_CAPACITY = 2
UPLOAD_RATE_REFILL_SECONDS = 60.0


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


async def _save_capped(upload: UploadFile, dest: Path, remaining: list[int]) -> None:
    """Stream `upload` to `dest`, enforcing the shared byte budget as it reads
    -- not after the fact, so an oversized upload is rejected mid-stream
    rather than fully buffered first."""
    with dest.open("wb") as out:
        while chunk := await upload.read(1024 * 1024):
            remaining[0] -= len(chunk)
            if remaining[0] < 0:
                raise _bad_request(
                    f"Upload exceeds the {MAX_UPLOAD_BYTES}-byte cap "
                    f"({MAX_UPLOAD_BYTES // (1024 * 1024)} MiB)."
                )
            out.write(chunk)


def _parse_metadata(
    clip_id: str,
    scene: str,
    slate: str,
    take: str,
    reel: str,
    tc_start_s: str,
    location: str,
    day_night: str,
    int_ext: str,
    characters_expected: str,
    fps: str,
) -> tuple[dict, int]:
    """Validates and normalizes the form fields. Returns (meta, fps_int).

    Nothing about the clip's identity is inferred or invented here -- every
    value either comes straight from the form or is one of ingest_all()'s
    existing empty defaults.
    """
    if not CLIP_ID_RE.match(clip_id):
        raise _bad_request(f"clip_id must match {CLIP_ID_RE.pattern!r}, got {clip_id!r}.")
    if not scene.strip():
        raise _bad_request("scene is required.")
    if not slate.strip():
        raise _bad_request("slate is required.")
    if not take.strip():
        raise _bad_request("take is required.")

    try:
        take_int = int(take)
    except ValueError:
        raise _bad_request(f"take must be an integer, got {take!r}.") from None

    tc_start = 0.0
    if tc_start_s.strip():
        try:
            tc_start = float(tc_start_s)
        except ValueError:
            raise _bad_request(f"tc_start_s must be a number, got {tc_start_s!r}.") from None

    fps_int = DEFAULT_FPS
    if fps.strip():
        try:
            fps_int = int(float(fps))
        except ValueError:
            raise _bad_request(f"fps must be a number, got {fps!r}.") from None

    characters = [c.strip() for c in characters_expected.split(",") if c.strip()]

    meta = {
        "scene": scene,
        "slate": slate,
        "take": take_int,
        "reel": reel,
        "tc_start_s": tc_start,
        "location": location,
        "day_night": day_night,
        "int_ext": int_ext,
        "characters_expected": characters,
    }
    return meta, fps_int


async def upload_footage(
    session_id: str = Form(...),
    clip_id: str = Form(...),
    scene: str = Form(...),
    slate: str = Form(...),
    take: str = Form(...),
    reel: str = Form(""),
    tc_start_s: str = Form(""),
    location: str = Form(""),
    day_night: str = Form(""),
    int_ext: str = Form(""),
    characters_expected: str = Form(""),
    fps: str = Form(""),
    mp4: UploadFile | None = File(None),  # noqa: B008 — FastAPI's own idiom for file params
    frames: list[UploadFile] | None = File(None),  # noqa: B008
) -> dict:
    if not allow(
        session_id,
        namespace=UPLOAD_RATE_NAMESPACE,
        capacity=UPLOAD_RATE_CAPACITY,
        refill_seconds=UPLOAD_RATE_REFILL_SECONDS,
    ):
        wait_s = math.ceil(
            retry_after(
                session_id,
                namespace=UPLOAD_RATE_NAMESPACE,
                capacity=UPLOAD_RATE_CAPACITY,
                refill_seconds=UPLOAD_RATE_REFILL_SECONDS,
            )
        )
        raise HTTPException(
            status_code=429,
            detail="Too many uploads. Please wait a moment and try again.",
            headers={"Retry-After": str(wait_s)},
        )

    has_mp4 = bool(mp4 is not None and mp4.filename)
    has_frames = bool(frames)
    if has_mp4 == has_frames:
        raise _bad_request("Provide exactly one of `mp4` or `frames`.")

    meta, fps_int = _parse_metadata(
        clip_id,
        scene,
        slate,
        take,
        reel,
        tc_start_s,
        location,
        day_night,
        int_ext,
        characters_expected,
        fps,
    )

    if has_mp4:
        ext = Path(mp4.filename or "").suffix.lower()
        if ext != ".mp4":
            raise _bad_request(f"mp4 file must have a .mp4 extension, got {mp4.filename!r}.")
        if mp4.content_type not in ALLOWED_MP4_CONTENT_TYPES:
            raise _bad_request(f"mp4 file has unsupported content type {mp4.content_type!r}.")
    else:
        if len(frames) > MAX_FRAMES:
            raise _bad_request(f"Too many frames ({len(frames)}); max is {MAX_FRAMES}.")
        for f in frames:
            ext = Path(f.filename or "").suffix.lower()
            if ext not in ALLOWED_FRAME_EXTS:
                raise _bad_request(
                    f"Frame {f.filename!r} has unsupported extension {ext!r}; "
                    "expected .jpg, .jpeg, or .png."
                )
            if f.content_type not in ALLOWED_FRAME_CONTENT_TYPES:
                raise _bad_request(
                    f"Frame {f.filename!r} has unsupported content type {f.content_type!r}."
                )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        remaining = [MAX_UPLOAD_BYTES]

        if has_mp4:
            mp4_path = tmp_dir / "upload.mp4"
            await _save_capped(mp4, mp4_path, remaining)
        else:
            frame_paths = []
            for i, f in enumerate(frames):
                ext = Path(f.filename).suffix.lower()
                frame_path = tmp_dir / f"frame_{i:06d}{ext}"
                await _save_capped(f, frame_path, remaining)
                frame_paths.append(frame_path)
            try:
                mp4_path = frames_to_mp4(frame_paths, tmp_dir / "encoded.mp4", fps=fps_int)
            except EncodeError as exc:
                raise _bad_request(f"Could not encode frames to video: {exc}") from exc

        duration = _probe_duration(mp4_path)
        if duration is None:
            raise _bad_request("Uploaded file is not decodable as video.")

        clip_blob = f"clips/{clip_id}.mp4"
        gcs_uri = f"gs://{config.GCS_BUCKET}/{clip_blob}"
        upload_blob(str(mp4_path), clip_blob, content_type="video/mp4")

        try:
            analysis = analyse_clip(clip_id, gcs_uri, clip_duration_s=duration)
            clip_rows, dialogue_rows, visual_rows = build_rows(
                analysis.model_dump(), meta, duration
            )
            insert_rows(clip_rows, dialogue_rows, visual_rows)

            poster_path = tmp_dir / "poster.jpg"
            _extract_poster_from(mp4_path, duration, poster_path)
            upload_blob(str(poster_path), f"posters/{clip_id}.jpg", content_type="image/jpeg")
        except Exception as exc:
            delete_blob(clip_blob)
            raise HTTPException(
                status_code=502,
                detail=f"Ingest failed after upload ({exc.__class__.__name__}): {exc}",
            ) from exc

    row = clip_summary_row(clip_id)
    if row is None:
        raise HTTPException(
            status_code=502, detail="Clip was ingested but is not yet visible in the index."
        )
    return row
