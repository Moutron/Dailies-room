"""Signed playback URLs and contact-strip thumbnails for a clip.

The bucket (`agent.config.GCS_BUCKET`) has no public/allUsers binding, so the
browser can never hit GCS directly — every playback URL is a short-lived V4
signed URL minted here, server-side, and handed to the <video> element.

Local ADC (a user's `gcloud auth application-default login` token) has no
private key to sign with, so signing goes through the IAM `signBlob` API
instead, impersonating a service account that has been granted
`roles/iam.serviceAccountTokenCreator` on itself. On Cloud Run the runtime
service account's own metadata credentials work the same way, granted the
same self-bound role — see docs/UI.md for the exact grants made.
"""

import os
from datetime import timedelta
from functools import lru_cache

import google.auth
from google.auth.transport.requests import Request
from google.cloud import storage

from agent import config

SIGNER_SA_EMAIL = os.environ["GCS_SIGNER_SA"]
URL_TTL = timedelta(minutes=15)


@lru_cache
def _storage_client() -> storage.Client:
    return storage.Client(project=config.PROJECT_ID)


def _credentials():
    creds, _ = google.auth.default()
    creds.refresh(Request())
    return creds


def signed_clip_url(clip_id: str) -> str:
    """A short-lived, signed GET URL for `clips/{clip_id}.mp4`."""
    blob = _storage_client().bucket(config.GCS_BUCKET).blob(f"clips/{clip_id}.mp4")
    creds = _credentials()
    return blob.generate_signed_url(
        version="v4",
        expiration=URL_TTL,
        method="GET",
        service_account_email=SIGNER_SA_EMAIL,
        access_token=creds.token,
    )


THUMBS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "thumbs")
THUMB_INTERVAL_S = 2.0  # matches the ffmpeg `fps=0.5` used to generate them


def thumbnails(clip_id: str) -> list[dict]:
    """Contact-strip frames for a clip: filename + the timecode it represents.

    Frames were extracted offline at a fixed 0.5 fps starting at t=0, so frame
    N's timestamp is exactly (N-1) * THUMB_INTERVAL_S — no need to probe each
    jpg, the naming convention already encodes it.
    """
    from agent.tools.search import timecode

    if not os.path.isdir(THUMBS_DIR):
        return []
    names = sorted(
        f for f in os.listdir(THUMBS_DIR) if f.startswith(f"{clip_id}_") and f.endswith(".jpg")
    )
    frames = []
    for i, name in enumerate(names):
        start_s = i * THUMB_INTERVAL_S
        frames.append(
            {
                "file": name,
                "start_s": start_s,
                "timecode": timecode(start_s),
            }
        )
    return frames
