"""Tests for ui/server/upload.py's POST /ingest/upload endpoint.

Gemini, GCS, ClickHouse, and ffmpeg are all mocked out -- these tests only
exercise the endpoint's own validation, rate limiting, orchestration, and
cleanup logic.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agent import config
from pipeline.ingest import CLIP_COLUMNS
from ui.server import rate_limit
from ui.server.main import app
from ui.server.upload import UPLOAD_RATE_CAPACITY

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    rate_limit._buckets.clear()
    rate_limit._namespaced_buckets.clear()


BASE_FORM = {
    "session_id": "s1",
    "clip_id": "clip_1",
    "scene": "S01",
    "slate": "1A",
    "take": "2",
}


def _mp4_file(content=b"fake-mp4-bytes", content_type="video/mp4", filename="upload.mp4"):
    return {"mp4": (filename, content, content_type)}


def _fake_analysis():
    analysis = MagicMock()
    analysis.model_dump.return_value = {
        "clip_id": "clip_1",
        "summary": "s",
        "dominant_mood": "m",
        "characters_present": [],
        "technical_notes": [],
        "dialogue": [],
        "visuals": [],
    }
    return analysis


class TestValidation:
    def test_missing_required_field_is_422(self):
        form = dict(BASE_FORM)
        del form["scene"]
        resp = client.post("/ingest/upload", data=form, files=_mp4_file())
        assert resp.status_code == 422

    def test_bad_clip_id_is_422_with_specific_message(self):
        form = {**BASE_FORM, "clip_id": "Bad Clip!"}
        resp = client.post("/ingest/upload", data=form, files=_mp4_file())
        assert resp.status_code == 422
        assert "clip_id" in resp.json()["detail"]

    def test_take_not_an_integer_is_422(self):
        form = {**BASE_FORM, "take": "two"}
        resp = client.post("/ingest/upload", data=form, files=_mp4_file())
        assert resp.status_code == 422
        assert "take" in resp.json()["detail"]

    def test_tc_start_s_not_a_number_is_422(self):
        form = {**BASE_FORM, "tc_start_s": "not-a-number"}
        resp = client.post("/ingest/upload", data=form, files=_mp4_file())
        assert resp.status_code == 422
        assert "tc_start_s" in resp.json()["detail"]

    def test_neither_mp4_nor_frames_is_422(self):
        resp = client.post("/ingest/upload", data=BASE_FORM)
        assert resp.status_code == 422
        assert "exactly one" in resp.json()["detail"]

    def test_both_mp4_and_frames_is_422(self):
        files = [
            ("mp4", ("a.mp4", b"x", "video/mp4")),
            ("frames", ("f1.jpg", b"x", "image/jpeg")),
        ]
        resp = client.post("/ingest/upload", data=BASE_FORM, files=files)
        assert resp.status_code == 422
        assert "exactly one" in resp.json()["detail"]

    def test_wrong_mp4_extension_is_422(self):
        resp = client.post("/ingest/upload", data=BASE_FORM, files=_mp4_file(filename="upload.mov"))
        assert resp.status_code == 422
        assert "extension" in resp.json()["detail"]

    def test_wrong_mp4_content_type_is_422(self):
        resp = client.post(
            "/ingest/upload",
            data=BASE_FORM,
            files=_mp4_file(content_type="application/octet-stream"),
        )
        assert resp.status_code == 422
        assert "content type" in resp.json()["detail"]

    def test_wrong_frame_extension_is_422(self):
        files = [("frames", ("frame_1.gif", b"x", "image/gif"))]
        resp = client.post("/ingest/upload", data=BASE_FORM, files=files)
        assert resp.status_code == 422
        assert "extension" in resp.json()["detail"]

    def test_too_many_frames_is_422(self):
        with patch("ui.server.upload.MAX_FRAMES", 2):
            files = [("frames", (f"frame_{i}.jpg", b"x", "image/jpeg")) for i in range(3)]
            resp = client.post("/ingest/upload", data=BASE_FORM, files=files)
        assert resp.status_code == 422
        assert "Too many frames" in resp.json()["detail"]

    def test_oversize_upload_is_422(self):
        with patch("ui.server.upload.MAX_UPLOAD_BYTES", 10):
            resp = client.post(
                "/ingest/upload", data=BASE_FORM, files=_mp4_file(content=b"x" * 1000)
            )
        assert resp.status_code == 422
        assert "cap" in resp.json()["detail"]

    def test_undecodable_file_is_422(self):
        with patch("ui.server.upload._probe_duration", return_value=None):
            resp = client.post("/ingest/upload", data=BASE_FORM, files=_mp4_file())
        assert resp.status_code == 422
        assert "decodable" in resp.json()["detail"]


class TestHappyPath:
    def test_mp4_mode_forwards_user_metadata_verbatim_to_insert_rows(self):
        form = {
            **BASE_FORM,
            "reel": "A007",
            "tc_start_s": "3600",
            "location": "canal bridge",
            "day_night": "DAY",
            "int_ext": "EXT",
            "characters_expected": "ELI, THOM",
        }
        fake_row = {"clip_id": "clip_1", "duration_s": 5.0, "state": "READY"}

        with (
            patch("ui.server.upload._probe_duration", return_value=5.0),
            patch("ui.server.upload.upload_blob") as mock_upload_blob,
            patch("ui.server.upload.analyse_clip", return_value=_fake_analysis()) as mock_analyse,
            patch("ui.server.upload.insert_rows") as mock_insert_rows,
            patch("ui.server.upload._extract_poster_from"),
            patch("ui.server.upload.clip_summary_row", return_value=fake_row),
        ):
            resp = client.post("/ingest/upload", data=form, files=_mp4_file())

        assert resp.status_code == 200
        assert resp.json() == fake_row

        mock_analyse.assert_called_once()
        assert mock_analyse.call_args.args[0] == "clip_1"
        assert mock_analyse.call_args.args[1] == f"gs://{config.GCS_BUCKET}/clips/clip_1.mp4"

        clip_rows, dialogue_rows, visual_rows = mock_insert_rows.call_args.args
        clip_row = dict(zip(CLIP_COLUMNS, clip_rows[0]))
        assert clip_row["clip_id"] == "clip_1"
        assert clip_row["scene"] == "S01"
        assert clip_row["slate"] == "1A"
        assert clip_row["take"] == 2
        assert clip_row["location"] == "canal bridge"
        assert clip_row["day_night"] == "DAY"
        assert clip_row["int_ext"] == "EXT"
        assert clip_row["characters_expected"] == ["ELI", "THOM"]
        assert clip_row["reel"] == "A007"
        assert clip_row["tc_start_s"] == 3600.0
        assert dialogue_rows == []
        assert visual_rows == []

        mock_upload_blob.assert_any_call(
            mock_upload_blob.call_args_list[0].args[0],
            "clips/clip_1.mp4",
            content_type="video/mp4",
        )

    def test_frames_mode_encodes_then_ingests(self, tmp_path):
        files = [("frames", (f"frame_{i}.jpg", b"x", "image/jpeg")) for i in range(3)]
        fake_row = {"clip_id": "clip_1", "duration_s": 2.0, "state": "READY"}
        encoded_path = tmp_path / "encoded.mp4"
        encoded_path.write_bytes(b"fake")

        with (
            patch("ui.server.upload.frames_to_mp4", return_value=encoded_path) as mock_encode,
            patch("ui.server.upload._probe_duration", return_value=2.0),
            patch("ui.server.upload.upload_blob"),
            patch("ui.server.upload.analyse_clip", return_value=_fake_analysis()),
            patch("ui.server.upload.insert_rows"),
            patch("ui.server.upload._extract_poster_from"),
            patch("ui.server.upload.clip_summary_row", return_value=fake_row),
        ):
            resp = client.post("/ingest/upload", data=BASE_FORM, files=files)

        assert resp.status_code == 200
        assert resp.json() == fake_row
        mock_encode.assert_called_once()
        frame_paths, _out_path = mock_encode.call_args.args
        assert len(frame_paths) == 3

    def test_no_visible_row_after_ingest_is_502(self):
        with (
            patch("ui.server.upload._probe_duration", return_value=5.0),
            patch("ui.server.upload.upload_blob"),
            patch("ui.server.upload.analyse_clip", return_value=_fake_analysis()),
            patch("ui.server.upload.insert_rows"),
            patch("ui.server.upload._extract_poster_from"),
            patch("ui.server.upload.clip_summary_row", return_value=None),
        ):
            resp = client.post("/ingest/upload", data=BASE_FORM, files=_mp4_file())
        assert resp.status_code == 502


class TestBlobCleanupOnFailure:
    def test_deletes_clip_blob_when_analyse_clip_raises(self):
        with (
            patch("ui.server.upload._probe_duration", return_value=5.0),
            patch("ui.server.upload.upload_blob"),
            patch("ui.server.upload.analyse_clip", side_effect=RuntimeError("gemini boom")),
            patch("ui.server.upload.delete_blob") as mock_delete,
        ):
            resp = client.post("/ingest/upload", data=BASE_FORM, files=_mp4_file())

        assert resp.status_code == 502
        assert "gemini boom" in resp.json()["detail"]
        mock_delete.assert_called_once_with("clips/clip_1.mp4")

    def test_deletes_clip_blob_when_insert_rows_raises(self):
        with (
            patch("ui.server.upload._probe_duration", return_value=5.0),
            patch("ui.server.upload.upload_blob"),
            patch("ui.server.upload.analyse_clip", return_value=_fake_analysis()),
            patch("ui.server.upload.insert_rows", side_effect=RuntimeError("clickhouse boom")),
            patch("ui.server.upload.delete_blob") as mock_delete,
        ):
            resp = client.post("/ingest/upload", data=BASE_FORM, files=_mp4_file())

        assert resp.status_code == 502
        mock_delete.assert_called_once_with("clips/clip_1.mp4")

    def test_deletes_clip_blob_when_poster_extraction_raises(self):
        with (
            patch("ui.server.upload._probe_duration", return_value=5.0),
            patch("ui.server.upload.upload_blob"),
            patch("ui.server.upload.analyse_clip", return_value=_fake_analysis()),
            patch("ui.server.upload.insert_rows"),
            patch("ui.server.upload._extract_poster_from", side_effect=RuntimeError("ffmpeg boom")),
            patch("ui.server.upload.delete_blob") as mock_delete,
        ):
            resp = client.post("/ingest/upload", data=BASE_FORM, files=_mp4_file())

        assert resp.status_code == 502
        mock_delete.assert_called_once_with("clips/clip_1.mp4")


class TestRateLimit:
    def test_429_once_upload_bucket_is_exhausted(self):
        with (
            patch("ui.server.upload._probe_duration", return_value=5.0),
            patch("ui.server.upload.upload_blob"),
            patch("ui.server.upload.analyse_clip", return_value=_fake_analysis()),
            patch("ui.server.upload.insert_rows"),
            patch("ui.server.upload._extract_poster_from"),
            patch(
                "ui.server.upload.clip_summary_row",
                return_value={"clip_id": "clip_1", "state": "READY"},
            ),
        ):
            for _ in range(UPLOAD_RATE_CAPACITY):
                resp = client.post("/ingest/upload", data=BASE_FORM, files=_mp4_file())
                assert resp.status_code == 200
            resp = client.post("/ingest/upload", data=BASE_FORM, files=_mp4_file())

        assert resp.status_code == 429
        assert "retry-after" in resp.headers

    def test_upload_bucket_is_independent_of_chat_bucket(self):
        """Exhausting /chat's bucket for a session must not affect that same
        session's upload allowance -- they're different namespaces."""
        for _ in range(rate_limit.CAPACITY):
            assert rate_limit.allow("shared-session") is True
        assert rate_limit.allow("shared-session") is False

        with (
            patch("ui.server.upload._probe_duration", return_value=5.0),
            patch("ui.server.upload.upload_blob"),
            patch("ui.server.upload.analyse_clip", return_value=_fake_analysis()),
            patch("ui.server.upload.insert_rows"),
            patch("ui.server.upload._extract_poster_from"),
            patch(
                "ui.server.upload.clip_summary_row",
                return_value={"clip_id": "clip_1", "state": "READY"},
            ),
        ):
            form = {**BASE_FORM, "session_id": "shared-session"}
            resp = client.post("/ingest/upload", data=form, files=_mp4_file())

        assert resp.status_code == 200
