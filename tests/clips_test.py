"""Tests for ui/server/clips.py."""

from unittest.mock import MagicMock, patch

from google.cloud.exceptions import NotFound

from ui.server.clips import delete_blob, signed_clip_url, thumbnails, upload_blob


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


class TestUploadBlob:
    def test_uploads_the_local_file_with_content_type(self):
        with patch("ui.server.clips._storage_client") as mock_storage:
            mock_blob = MagicMock()
            mock_storage.return_value.bucket.return_value.blob.return_value = mock_blob

            upload_blob("/tmp/x.mp4", "clips/clip_1.mp4", content_type="video/mp4")

            mock_storage.return_value.bucket.return_value.blob.assert_called_once_with(
                "clips/clip_1.mp4"
            )
            mock_blob.upload_from_filename.assert_called_once_with(
                "/tmp/x.mp4", content_type="video/mp4"
            )


class TestDeleteBlob:
    def test_deletes_an_existing_blob(self):
        with patch("ui.server.clips._storage_client") as mock_storage:
            mock_blob = MagicMock()
            mock_storage.return_value.bucket.return_value.blob.return_value = mock_blob

            delete_blob("clips/clip_1.mp4")

            mock_blob.delete.assert_called_once()

    def test_missing_blob_is_not_an_error(self):
        with patch("ui.server.clips._storage_client") as mock_storage:
            mock_blob = MagicMock()
            mock_blob.delete.side_effect = NotFound("gone")
            mock_storage.return_value.bucket.return_value.blob.return_value = mock_blob

            delete_blob("clips/does_not_exist.mp4")  # must not raise


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
