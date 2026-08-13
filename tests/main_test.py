"""Tests for ui/server/main.py's FastAPI routes.

The agent runner and clip-signing logic are mocked out here so these tests
don't need real Gemini or ClickHouse access.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ui.server import rate_limit
from ui.server.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    rate_limit._buckets.clear()


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_chat_streams_sse_from_stream_chat():
    async def fake_stream(message, session_id):
        yield 'event: message\ndata: {"text": "hi", "final": true}\n\n'
        yield "event: done\ndata: {}\n\n"

    with patch("ui.server.main.stream_chat", fake_stream):
        resp = client.post("/chat", json={"message": "hello", "session_id": "s1"})

    assert resp.status_code == 200
    assert "event: message" in resp.text
    assert "event: done" in resp.text


def test_chat_returns_429_once_rate_limit_is_exhausted():
    async def fake_stream(message, session_id):
        yield "event: done\ndata: {}\n\n"

    with patch("ui.server.main.stream_chat", fake_stream):
        for _ in range(rate_limit.CAPACITY):
            resp = client.post("/chat", json={"message": "hi", "session_id": "rl-test"})
            assert resp.status_code == 200

        resp = client.post("/chat", json={"message": "hi", "session_id": "rl-test"})

    assert resp.status_code == 429


def test_clip_url_returns_signed_url():
    with patch("ui.server.main.signed_clip_url", return_value="https://signed.example/x.mp4"):
        resp = client.get("/clip/clip_1/url")

    assert resp.status_code == 200
    assert resp.json() == {"url": "https://signed.example/x.mp4"}


def test_clip_url_failure_returns_502():
    with patch("ui.server.main.signed_clip_url", side_effect=RuntimeError("no creds")):
        resp = client.get("/clip/clip_1/url")

    assert resp.status_code == 502
    assert "RuntimeError" in resp.json()["detail"]


def test_clip_thumbnails_wraps_frames():
    frames = [{"file": "clip_1_001.jpg", "start_s": 0.0, "timecode": "00:00:00:00"}]
    with patch("ui.server.main.thumbnails", return_value=frames):
        resp = client.get("/clip/clip_1/thumbnails")

    assert resp.status_code == 200
    assert resp.json() == {"frames": frames}


def test_thumb_file_404s_when_missing(tmp_path):
    with patch("ui.server.main.THUMBS_DIR", str(tmp_path)):
        resp = client.get("/thumbs/does-not-exist.jpg")

    assert resp.status_code == 404


def test_thumb_file_serves_existing_file(tmp_path):
    (tmp_path / "frame.jpg").write_bytes(b"fake-jpeg-bytes")
    with patch("ui.server.main.THUMBS_DIR", str(tmp_path)):
        resp = client.get("/thumbs/frame.jpg")

    assert resp.status_code == 200
    assert resp.content == b"fake-jpeg-bytes"


def test_thumb_file_blocks_path_traversal_outside_thumbs_dir(tmp_path):
    # Routed through TestClient/httpx, a "../" segment never reaches this
    # handler as a single path param -- Starlette's own routing already
    # rejects it before thumb_file() runs. Call the handler directly instead,
    # so this test actually exercises the resolved-path guard rather than
    # relying on the HTTP layer to have caught it first (a different ASGI
    # front end, or a route change to `{filename:path}`, could let a
    # slash-bearing value through).
    from fastapi import HTTPException

    from ui.server.main import thumb_file

    thumbs_dir = tmp_path / "thumbs"
    thumbs_dir.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"do-not-serve-me")

    with patch("ui.server.main.THUMBS_DIR", str(thumbs_dir)):
        try:
            thumb_file("../secret.txt")
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("expected thumb_file to reject a path-traversal filename")
