"""Tests for ui/server/clips.py."""

from unittest.mock import MagicMock, patch

from ui.server.clips import signed_clip_url, thumbnails


class TestSignedClipUrl:
    def test_signs_url_via_storage_client_and_credentials(self):
        with (
            patch("ui.server.clips._storage_client") as mock_storage,
            patch("ui.server.clips._credentials") as mock_creds,
        ):
            mock_blob = MagicMock()
            mock_blob.generate_signed_url.return_value = "https://signed.example/clip.mp4"
            mock_storage.return_value.bucket.return_value.blob.return_value = mock_blob
            mock_creds.return_value.token = "fake-token"

            url = signed_clip_url("03_2a_take")

            assert url == "https://signed.example/clip.mp4"
            mock_storage.return_value.bucket.return_value.blob.assert_called_once_with(
                "clips/03_2a_take.mp4"
            )
            _, kwargs = mock_blob.generate_signed_url.call_args
            assert kwargs["version"] == "v4"
            assert kwargs["method"] == "GET"
            assert kwargs["access_token"] == "fake-token"


class TestThumbnails:
    def test_missing_dir_returns_empty_list(self, tmp_path):
        with patch("ui.server.clips.THUMBS_DIR", str(tmp_path / "does-not-exist")):
            assert thumbnails("clip_1") == []

    def test_lists_matching_frames_with_computed_timecodes(self, tmp_path):
        (tmp_path / "clip_1_001.jpg").write_bytes(b"")
        (tmp_path / "clip_1_002.jpg").write_bytes(b"")
        (tmp_path / "clip_2_001.jpg").write_bytes(b"")  # different clip, must be excluded
        (tmp_path / "clip_1_notes.txt").write_bytes(b"")  # wrong extension, must be excluded

        with patch("ui.server.clips.THUMBS_DIR", str(tmp_path)):
            frames = thumbnails("clip_1")

        assert [f["file"] for f in frames] == ["clip_1_001.jpg", "clip_1_002.jpg"]
        assert frames[0]["start_s"] == 0.0
        assert frames[0]["timecode"] == "00:00:00:00"
        assert frames[1]["start_s"] == 2.0
        assert frames[1]["timecode"] == "00:00:02:00"
