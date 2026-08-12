"""Dummy env vars so importing agent/pipeline/ui code doesn't crash under test.

agent/config.py reads several os.environ[...] vars unconditionally at import
time, with no defaults, because it doubles as config for two live
deployments (Cloud Run and Vertex AI Agent Engine). CI sets none of these, so
anything that transitively imports agent.config (agent.agent, agent.tools.*,
pipeline.ingest, pipeline.embed, ui.server.*) would raise KeyError during
test collection without this running first. Set with setdefault, at module
scope, so this executes before any test module is imported — agent.config's
own load_dotenv(override=True) still wins locally where a real .env exists.
"""

import os

os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("GCS_BUCKET", "test-bucket")
os.environ.setdefault("GEMINI_VIDEO_MODEL", "test-video-model")
os.environ.setdefault("GEMINI_AGENT_MODEL", "test-agent-model")
os.environ.setdefault("CLICKHOUSE_HOST", "test-clickhouse-host")
os.environ.setdefault("GCS_SIGNER_SA", "signer@test-project.iam.gserviceaccount.com")
