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


def test_chat_429_carries_a_real_retry_after_header():
    async def fake_stream(message, session_id):
        yield "event: done\ndata: {}\n\n"

    with patch("ui.server.main.stream_chat", fake_stream):
        for _ in range(rate_limit.CAPACITY):
            client.post("/chat", json={"message": "hi", "session_id": "rl-header"})
        resp = client.post("/chat", json={"message": "hi", "session_id": "rl-header"})

    assert resp.status_code == 429
    retry_after = int(resp.headers["retry-after"])
    assert 0 < retry_after <= rate_limit.REFILL_SECONDS


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


def test_clip_meta_returns_the_metadata():
    meta = {"clip_id": "01_1a_take", "scene": "S01", "duration_s": 5.5}
    with patch("ui.server.main.clip_meta", return_value=meta):
        resp = client.get("/clip/01_1a_take/meta")

    assert resp.status_code == 200
    assert resp.json() == meta


def test_clip_meta_404s_when_the_clip_is_not_indexed():
    with patch("ui.server.main.clip_meta", return_value=None):
        resp = client.get("/clip/does_not_exist/meta")

    assert resp.status_code == 404


def test_clip_dialogue_returns_the_lines():
    lines = [
        {
            "segment_idx": 0,
            "start_s": 0.0,
            "end_s": 3.8,
            "speaker": "ELI",
            "text": "hi",
            "delivery": "flat",
        }
    ]
    with patch("ui.server.main.clip_dialogue", return_value=lines):
        resp = client.get("/clip/01_1a_take/dialogue")

    assert resp.status_code == 200
    assert resp.json() == {"lines": lines}


def test_clip_dialogue_returns_empty_list_for_a_real_zero_line_clip():
    with patch("ui.server.main.clip_dialogue", return_value=[]):
        resp = client.get("/clip/03_2a_take/dialogue")

    assert resp.status_code == 200
    assert resp.json() == {"lines": []}


def test_clip_dialogue_404s_when_the_clip_is_not_indexed():
    with patch("ui.server.main.clip_dialogue", return_value=None):
        resp = client.get("/clip/does_not_exist/dialogue")

    assert resp.status_code == 404


def test_stats_returns_real_index_numbers():
    with patch(
        "ui.server.main.index_stats", return_value={"clip_count": 6, "total_duration_s": 29.83}
    ):
        resp = client.get("/stats")

    assert resp.status_code == 200
    assert resp.json() == {"clip_count": 6, "total_duration_s": 29.83}


def test_coverage_matrix_returns_the_grid():
    matrix = {
        "columns": ["WIDE", "MED", "MCU", "CU", "INSERT"],
        "rows": [],
        "stats": {"takes_printed": 6, "scenes": 2, "gaps_flagged": 3},
        "gap_scenes": ["S01"],
        "headline": "Scene S01 is missing tight coverage.",
        "sql": "SELECT ...",
    }
    with patch("ui.server.main.coverage_matrix", return_value=matrix):
        resp = client.get("/coverage/matrix")

    assert resp.status_code == 200
    assert resp.json() == matrix


def test_clips_route_returns_the_list():
    clips = [
        {
            "clip_id": "01_1a_take",
            "reel": "A002",
            "scene": "S01",
            "slate": "1A",
            "take": 1,
            "duration_s": 4.8,
            "shot_type": "medium",
        }
    ]
    with patch("ui.server.main.clip_list", return_value=clips) as mock_clip_list:
        resp = client.get("/clips")

    assert resp.status_code == 200
    assert resp.json() == {"clips": clips}
    mock_clip_list.assert_called_once_with(reels=None, shot_types=None)


def test_clips_route_forwards_repeated_filter_params():
    with patch("ui.server.main.clip_list", return_value=[]) as mock_clip_list:
        resp = client.get("/clips?reel=A002&reel=A007&shot_type=WIDE")

    assert resp.status_code == 200
    mock_clip_list.assert_called_once_with(reels=["A002", "A007"], shot_types=["WIDE"])


def test_search_route_returns_hits():
    payload = {"query": "robotic hand", "mode": "semantic", "hits": []}
    with patch("ui.server.main.browse_search", return_value=payload) as mock_search:
        resp = client.get("/search?q=robotic+hand&mode=semantic")

    assert resp.status_code == 200
    assert resp.json() == payload
    mock_search.assert_called_once_with("robotic hand", "semantic")


def test_search_route_defaults_to_semantic_mode():
    with patch(
        "ui.server.main.browse_search", return_value={"query": "x", "mode": "semantic", "hits": []}
    ) as mock_search:
        client.get("/search?q=x")

    mock_search.assert_called_once_with("x", "semantic")


def test_search_route_rejects_an_unknown_mode():
    resp = client.get("/search?q=x&mode=fuzzy")

    assert resp.status_code == 400


def test_search_route_short_circuits_a_blank_query_without_hitting_the_index():
    with patch("ui.server.main.browse_search") as mock_search:
        resp = client.get("/search?q=")

    assert resp.status_code == 200
    assert resp.json() == {"query": "", "mode": "semantic", "hits": []}
    mock_search.assert_not_called()


def test_circle_clip_sets_circled_state():
    with patch(
        "ui.server.main.set_circled", return_value={"clip_id": "01_1a_take", "circled": True}
    ) as mock_set:
        resp = client.post("/clip/01_1a_take/circle", json={"circled": True})

    assert resp.status_code == 200
    assert resp.json() == {"clip_id": "01_1a_take", "circled": True}
    mock_set.assert_called_once_with("01_1a_take", True)


def test_circle_clip_404s_when_the_clip_is_not_indexed():
    with patch("ui.server.main.set_circled", return_value=None):
        resp = client.post("/clip/does_not_exist/circle", json={"circled": True})

    assert resp.status_code == 404


def test_shot_list_rows_returns_the_generated_rows():
    rows = [
        {
            "row_id": "S01-1A",
            "title": "S01 · 1A",
            "qualifier": "amsterdam canal bridge, day",
            "reason": "Nothing tighter than MED exists across the 3 takes for this slate.",
            "source_clip": "01_1a_take",
            "classification": "coverage gap",
            "selected": False,
        }
    ]
    with patch("ui.server.main.list_rows", return_value=rows):
        resp = client.get("/shot-list/rows")

    assert resp.status_code == 200
    assert resp.json() == {"rows": rows}


def test_shot_list_select_toggles_a_row():
    row = {"row_id": "S01-1A", "title": "S01 · 1A", "selected": True}
    with patch("ui.server.main.set_selected", return_value=row) as mock_select:
        resp = client.post("/shot-list/rows/S01-1A/select", json={"selected": True})

    assert resp.status_code == 200
    assert resp.json() == row
    mock_select.assert_called_once_with("S01-1A", True)


def test_shot_list_select_404s_for_an_unknown_row():
    with patch("ui.server.main.set_selected", return_value=None):
        resp = client.post("/shot-list/rows/does-not-exist/select", json={"selected": True})

    assert resp.status_code == 404


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


def test_poster_file_404s_when_missing(tmp_path):
    with patch("ui.server.main.POSTERS_DIR", str(tmp_path)):
        resp = client.get("/posters/does-not-exist.jpg")

    assert resp.status_code == 404


def test_poster_file_serves_existing_file(tmp_path):
    (tmp_path / "clip_1.jpg").write_bytes(b"fake-jpeg-bytes")
    with patch("ui.server.main.POSTERS_DIR", str(tmp_path)):
        resp = client.get("/posters/clip_1.jpg")

    assert resp.status_code == 200
    assert resp.content == b"fake-jpeg-bytes"


def test_poster_file_blocks_path_traversal_outside_posters_dir(tmp_path):
    from fastapi import HTTPException

    from ui.server.main import poster_file

    posters_dir = tmp_path / "posters"
    posters_dir.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"do-not-serve-me")

    with patch("ui.server.main.POSTERS_DIR", str(posters_dir)):
        try:
            poster_file("../secret.txt")
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("expected poster_file to reject a path-traversal filename")


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
