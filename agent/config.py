"""Config. Secrets from Secret Manager when deployed, env vars locally."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# An explicit path, not dotenv's default stack-frame/cwd search: that search
# was observed to be non-deterministic depending on how the interpreter was
# invoked (heredoc/-c have no reliable __file__, so it falls back to
# os.getcwd(), which isn't always the repo root) — same .env, same process,
# sometimes not found. Anchoring to this file's own location is exact.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=True)


@lru_cache
def _secret(secret_id: str) -> str:
    """Read a secret, preferring a local env var for development."""
    env_key = secret_id.upper().replace("-", "_")
    if local := os.getenv(env_key):
        return local

    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{os.environ['GCP_PROJECT_ID']}" f"/secrets/{secret_id}/versions/latest"
    return client.access_secret_version(request={"name": name}).payload.data.decode()


PROJECT_ID = os.environ["GCP_PROJECT_ID"]
LOCATION = os.getenv("GCP_LOCATION", "us-central1")
GCS_BUCKET = os.environ["GCS_BUCKET"]

VIDEO_MODEL = os.environ["GEMINI_VIDEO_MODEL"]
AGENT_MODEL = os.environ["GEMINI_AGENT_MODEL"]

CH_HOST = os.environ["CLICKHOUSE_HOST"]
CH_PORT = int(os.getenv("CLICKHOUSE_PORT", "8443"))
CH_USER = os.getenv("CLICKHOUSE_USER", "default")
CH_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "dailies")
# ClickHouse Cloud requires TLS (port 8443). The local Docker fallback
# (docker-compose.clickhouse.yml, docs/RUNBOOK.md) serves plain HTTP on
# 8123, so this must be toggleable rather than hardcoded.
CH_SECURE = os.getenv("CLICKHOUSE_SECURE", "true").lower() not in ("false", "0", "")


def ch_password() -> str:
    return _secret("clickhouse-password")
