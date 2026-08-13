# Runbook

Everything needed to run, deploy, and tear down The Dailies Room, in the
order you'd actually do it. Written and then verified by cloning into a
fresh directory and following it literally — see "Clean-clone
verification" at the bottom for what that caught.

## Prerequisites and versions

- Python 3.12 (repo requires `>=3.10`; developed and deployed on 3.12).
- Node.js 20+ (for `ui/`, Vite 8).
- `gcloud` CLI, authenticated (`gcloud auth login` +
  `gcloud auth application-default login`) against a project with billing
  enabled.
- `ffmpeg`/`ffprobe` on `PATH` (used by `pipeline/ingest.py` for clip
  duration clamping — optional at ingest time, but recommended).
- Docker, only if you want the local ClickHouse fallback (see below) —
  not needed for the Cloud-backed path.
- `google-adk==2.6.3` pinned (`requirements.lock`). Verify any Agent
  Engine quickstart you follow matches this exact minor version — the
  deploy/session API shape has moved across 2.x releases (see "Deploy the
  agent" below for what actually worked against 2.6.3).

## Local setup from a clean clone

```bash
git clone https://github.com/Moutron/Dailies-room.git
cd Dailies-room

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ui]"

cp .env.example .env
# Edit .env:
#   GCP_PROJECT_ID, GOOGLE_CLOUD_PROJECT  -> your project id
#   GCS_BUCKET                            -> your bucket (or leave as-is
#                                            to read this project's public
#                                            dataset, if still available)
#   GEMINI_VIDEO_MODEL, GEMINI_AGENT_MODEL -> e.g. gemini-2.5-flash
#   CLICKHOUSE_HOST / CLICKHOUSE_DATABASE  -> your ClickHouse Cloud
#                                            instance, or leave the
#                                            defaults and use the local
#                                            Docker fallback below instead
#   CLICKHOUSE_PASSWORD                    -> only set locally, never
#                                            commit; leave blank to read
#                                            from Secret Manager instead
```

**Missing-step #1, found by the clean-clone test:** `.env.example` didn't
include `GOOGLE_GENAI_USE_VERTEXAI` / `GOOGLE_CLOUD_PROJECT` /
`GOOGLE_CLOUD_LOCATION` — `google-genai`'s *own* env vars, not this
project's (`GCP_PROJECT_ID`/`GCP_LOCATION`), needed to route model calls
through Vertex AI instead of the public Gemini API. Both `.env.example`
and this project's `.env` now set them. Without this, every model call
fails with `ValueError: No API key was provided.` even though the app's
own config vars are all correctly set — an easy trap since the error
message points at API keys, not Vertex routing.

Run the backend and frontend in two terminals:

```bash
# terminal 1
source .venv/bin/activate
uvicorn ui.server.main:app --reload --port 8001

# terminal 2
cd ui && npm install && npm run dev
```

Open the Vite dev URL (typically `http://localhost:5173`) — it proxies
`/chat`, `/clip`, `/thumbs`, `/health` to the FastAPI backend on 8001
(`ui/vite.config.ts`), so there's no CORS setup needed.

## Rebuild the index without reprocessing video

`data/processed/*.json` (Gemini's video analysis output) and
`data/manifest.json` (shoot metadata) are both committed to the repo —
confirmed not gitignored (only `data/raw/`, `data/clips/`, and
`*.mp4`/`*.mov` are). This is what makes "clone and run it yourself"
actually true without paying for video analysis:

```bash
source .venv/bin/activate
python -m schema.clickhouse   # or: run schema/clickhouse.sql against your
                               # ClickHouse instance directly — creates
                               # the DailiesRoom database + 3 tables
python -m pipeline.ingest
```

`pipeline/ingest.py`'s `ingest_all()` reads `data/processed/*.json` +
`data/manifest.json`, embeds dialogue/visual text via Gemini (cheap —
embeddings, not video analysis), and truncates+inserts into
`clips`/`dialogue`/`visuals`. It's idempotent — safe to re-run any time.

**Missing-step #2, found by the clean-clone test:** there's no Python
entry point for `schema/clickhouse.sql` — it has to be applied directly
against ClickHouse (`clickhouse client < schema/clickhouse.sql` for a
local instance, or paste it into the ClickHouse Cloud SQL console). The
original instructions assumed a `python -m schema.clickhouse` command
that doesn't exist; corrected above.

## Local ClickHouse fallback (Docker)

For demo-day resilience if ClickHouse Cloud or the network is unavailable
— see `docker-compose.clickhouse.yml`:

```bash
docker compose -f docker-compose.clickhouse.yml up -d
# wait for the healthcheck (few seconds), then:
```

Point the app at it by overriding these in `.env` (or a separate
`.env.local`, loaded the same way):

```bash
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=local-dev-only
CLICKHOUSE_DATABASE=DailiesRoom
CLICKHOUSE_SECURE=false   # ClickHouse Cloud requires TLS; the local
                           # container serves plain HTTP on 8123
```

`agent/config.py::CH_SECURE` (added Phase 9.7) controls this — ClickHouse
Cloud (port 8443) always needs `secure=True`; this container (port 8123)
doesn't support TLS at all, so it must be `false`. Then run the schema +
ingest steps above against it — same commands, they just follow whatever
`CLICKHOUSE_*` vars are set.

**Missing-step #3, found by the clean-clone test:** `clickhouse_connect`
was hardcoded to `secure=True` everywhere (`pipeline/ingest.py::client()`),
which silently fails (or requires setting up TLS certs) against a plain
local container. Fixed by making it configurable via `CLICKHOUSE_SECURE`.

**Not yet tested end-to-end** — Docker Desktop's daemon was unreachable in
this environment for the whole of this session (`docker ps` hung /
`Cannot connect to the Docker daemon` even after a restart), so
`docker-compose.clickhouse.yml` and the `CH_SECURE` config path are
written and reviewed but not run. **Before relying on this as a demo-day
fallback, actually bring it up and run it once** with wifi off:
`docker compose -f docker-compose.clickhouse.yml up -d`, run the schema +
ingest steps above against it, then start the local UI and confirm
dialogue/visual search and coverage work with the network disconnected.
Note ahead of time: GCS-backed clip playback will **not** work offline
(needs network for both Gemini calls and signed URLs) even once this
passes — the local ClickHouse fallback only covers the agent's
search/reasoning path, not video playback, which is expected, not a bug.

## Deploy steps, in order

### 1. Cloud Run (`dailies-ui`)

Already deployed; redeploy after code changes with:

```bash
gcloud run deploy dailies-ui --source . --region=us-central1 --project=dailies-room
```

Runs as the dedicated `dailies-ui@dailies-room.iam.gserviceaccount.com`
service account (`--service-account` flag) — see `docs/SECURITY.md` for
its grants and the one documented broader-than-necessary grant left on
the Compute Engine default SA (project-level `storage.objectViewer`,
needed only for Cloud Build's source-tarball read during this exact
deploy command, unrelated to the runtime identity).

**Gotcha:** `ui/server/clips.py`'s signed-URL minting impersonates
whichever SA the `GCS_SIGNER_SA` env var names, via IAM `signBlob` —
it does **not** derive that from the runtime's own ambient credentials.
If you change `--service-account` on a redeploy, update `GCS_SIGNER_SA`
to match (`gcloud run services update dailies-ui --update-env-vars
GCS_SIGNER_SA=<new-sa-email>`) and make sure that SA has
`roles/iam.serviceAccountTokenCreator` **on itself** — otherwise clip
playback URLs fail with a generic `TransportError`, since the runtime
token's principal won't be authorized to impersonate the (now stale)
`GCS_SIGNER_SA`. Caught live during the Phase-A3 SA hardening: switching
Cloud Run to `dailies-ui` without updating this var broke `/clip/*/url`
until the env var was corrected.

### 2. Vertex AI Agent Engine (`dailies-agent`) — judging-day only, not left running

This is a **second, independent deployment target**, not a replacement for
the in-process runner `ui/server/agent_runner.py` uses — see
`docs/ARCHITECTURE.md` for why (different event shapes; Agent Engine
doesn't scale to zero, so leaving it up burns credits for no demo
benefit). Treat it as judging-day infrastructure: deploy it, verify it,
tear it down, redeploy fresh right before judging/demo recording.

Prerequisites:
- `pip install -e ".[deploy]"` (installs `google-cloud-aiplatform[adk,agent_engines]`
  — not needed for normal local dev, only for running this deploy).
- The `dailies-agent` service account exists with its four roles (see
  `docs/SECURITY.md`) — one-time setup, already done for this project:
  ```bash
  gcloud iam service-accounts create dailies-agent --display-name="Dailies Room Agent"
  gcloud projects add-iam-policy-binding dailies-room \
    --member="serviceAccount:dailies-agent@dailies-room.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user" --condition=None
  gcloud secrets add-iam-policy-binding clickhouse-password \
    --member="serviceAccount:dailies-agent@dailies-room.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
  gsutil iam ch serviceAccount:dailies-agent@dailies-room.iam.gserviceaccount.com:objectViewer \
    gs://dailies-room-dailies
  gcloud projects add-iam-policy-binding dailies-room \
    --member="serviceAccount:dailies-agent@dailies-room.iam.gserviceaccount.com" \
    --role="roles/logging.logWriter" --condition=None
  gcloud projects add-iam-policy-binding dailies-room \
    --member="serviceAccount:dailies-agent@dailies-room.iam.gserviceaccount.com" \
    --role="roles/cloudtrace.agent" --condition=None
  gcloud projects add-iam-policy-binding dailies-room \
    --member="serviceAccount:dailies-agent@dailies-room.iam.gserviceaccount.com" \
    --role="roles/monitoring.metricWriter" --condition=None
  gcloud iam service-accounts add-iam-policy-binding \
    dailies-agent@dailies-room.iam.gserviceaccount.com \
    --member="user:YOUR_EMAIL" --role="roles/iam.serviceAccountUser"
  ```
- `agent/.env` exists (gitignored — non-secret config only, no password;
  the deploy CLI's `--env_file` flag is a deprecated no-op in ADK 2.6.3,
  so it must read `agent/.env` by its own default convention):
  ```
  GCP_PROJECT_ID=dailies-room
  GCP_LOCATION=us-central1
  GCS_BUCKET=dailies-room-dailies
  GEMINI_VIDEO_MODEL=gemini-2.5-flash
  GEMINI_AGENT_MODEL=gemini-2.5-flash
  CLICKHOUSE_HOST=sus54l5t8w.us-central1.gcp.clickhouse.cloud
  CLICKHOUSE_PORT=8443
  CLICKHOUSE_USER=default
  CLICKHOUSE_DATABASE=DailiesRoom
  ```
- `agent/requirements.txt` exists with the app's real runtime deps
  (`google-genai`, `google-cloud-storage`, `google-cloud-secret-manager`,
  `clickhouse-connect`, `pydantic`, `python-dotenv`, `tenacity`) — without
  it, `adk deploy agent_engine` generates a minimal one containing only
  `google-adk`/`google-cloud-aiplatform`, and the container crashes with
  `ModuleNotFoundError: No module named 'clickhouse_connect'` on first
  tool call.
- `agent/.agent_engine_config.json` sets
  `{"service_account": "dailies-agent@dailies-room.iam.gserviceaccount.com"}`.

Deploy (first time — creates a new instance; capture the resource name it
prints):

```bash
source .venv/bin/activate
adk deploy agent_engine \
  --project=dailies-room \
  --region=us-central1 \
  --display_name="Dailies Room Agent" \
  --description="Answers questions about raw dailies footage from a film shoot." \
  --otel_to_cloud \
  --extra_packages=pipeline \
  agent
```

`--extra_packages=pipeline` is required — only the `agent/` folder is
staged by default, but `agent/tools/search.py` and `coverage.py` import
from the top-level `pipeline/` package. `--otel_to_cloud` enables tracing
and structured-log-friendly telemetry (Phase 9.3) — see
`docs/AGENT_QUALITY.md`'s "Inspecting a conversation's tool calls" section
for how to read it back.

**Known gap, not yet verified against a real Agent Engine deploy:**
`agent/tools/coverage.py`'s `_character_aliases()` reads `data/manifest.json`
from disk at request time (path resolved relative to the source file). The
Cloud Run image explicitly `COPY`s that file in (see `Dockerfile`); nothing
here stages it into the Agent Engine package, and `data/` isn't a Python
package `--extra_packages` can name. Confirm `get_coverage` works after
deploying (or redeploying) Agent Engine — if it fails, the error will
misleadingly say "the footage index is unreachable" rather than naming the
missing file (see `agent/tools/_errors.py`).

Redeploy to the **same** resource (updates in place, doesn't create a
duplicate) by adding `--agent_engine_id=<the resource name>`:

```bash
adk deploy agent_engine \
  --project=dailies-room --region=us-central1 \
  --display_name="Dailies Room Agent" \
  --agent_engine_id="projects/766122679114/locations/us-central1/reasoningEngines/2937096274219892736" \
  --otel_to_cloud --extra_packages=pipeline \
  agent
```

Query it directly (e.g. for judges, or your own smoke test):

```python
import vertexai
vertexai.init(project="dailies-room", location="us-central1")
from vertexai import agent_engines
ae = agent_engines.get("projects/766122679114/locations/us-central1/reasoningEngines/2937096274219892736")
for event in ae.stream_query(message="What coverage do we have of the S03 rooftop scene?", user_id="judge"):
    print(event)
```

## Secret rotation

`clickhouse-password` lives in Secret Manager:

```bash
echo -n "NEW_PASSWORD" | gcloud secrets versions add clickhouse-password \
  --project=dailies-room --data-file=-
```

Both deployments (`dailies-ui` on Cloud Run, `dailies-agent` on Agent
Engine) read it via `agent/config.py::ch_password()`'s Secret Manager
fallback and always fetch the `latest` version — no redeploy needed after
rotation, the next request picks it up (subject to `_secret()`'s
`@lru_cache`, which caches per *process*, so a running container keeps
its old value until it restarts — restart the Cloud Run revision or the
Agent Engine instance if you need the new password to take effect
immediately rather than on next cold start).

Update the ClickHouse Cloud user's actual password to match in the
ClickHouse Cloud console at the same time — Secret Manager only stores
what this app reads, it doesn't change ClickHouse's own credentials.

## Teardown (after judging)

**Do this immediately after judging/demo recording wraps — Agent Engine
does not scale to zero and bills continuously while it exists.**

```bash
# Delete the Agent Engine deployment entirely:
python3 -c "
import vertexai
vertexai.init(project='dailies-room', location='us-central1')
from vertexai import agent_engines
ae = agent_engines.get('projects/766122679114/locations/us-central1/reasoningEngines/2937096274219892736')
ae.delete()
"
```

Redeploy fresh right before judging/demo recording using the "Deploy the
agent" command above (omit `--agent_engine_id` to create a new instance,
or reuse the same ID if you noted it down — either works, a new ID just
means updating the query snippet above).

`dailies-ui` on Cloud Run already scales to zero (`min-instances` unset,
confirmed via `gcloud run services describe dailies-ui --region=us-central1
--format="yaml(spec.template.metadata.annotations)"` — no
`run.googleapis.com/minScale` annotation present) — nothing to tear down
there, it costs ~nothing while idle.

Local Docker ClickHouse, if you brought it up for the offline fallback:

```bash
docker compose -f docker-compose.clickhouse.yml down -v   # -v also drops the data volume
```

The budget alert (50%/80% of $50, Phase 9.4) stays in place — no reason
to remove it, it's free and doesn't require action.

## Clean-clone verification (Phase 9.5)

Copied the working tree into a fresh directory (fresh venv, no `.env`, no
`__pycache__`/`node_modules`/`.venv`) and followed this runbook literally.
Found four missing/broken steps, not three — all four are now fixed in
the codebase and in this runbook, not just noted:

1. `.env.example` was missing `GOOGLE_GENAI_USE_VERTEXAI` /
   `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` (see "Local setup"
   above).
2. No documented command to apply `schema/clickhouse.sql` (see "Rebuild
   the index" above).
3. `clickhouse_connect`'s hardcoded `secure=True` would have blocked the
   local Docker fallback (see "Local ClickHouse fallback" above).
4. **`.env.example`'s `CLICKHOUSE_PASSWORD=   # never fill in here` line
   silently broke the Secret Manager fallback.** `python-dotenv` does not
   strip inline `key=value  # comment` comments — everything after `=` on
   that line becomes the literal env var value, so `ch_password()` read
   the password as the literal string `"# never fill in here"` instead of
   falling back to Secret Manager, and `pipeline.ingest` failed with a
   ClickHouse authentication error. Caught because the clean-clone test
   actually ran ingest end-to-end rather than just reading the file. Fixed
   by moving the comment onto its own line above the (truly empty) var.

After all four fixes, ran `python -m pipeline.ingest` (`Ingested 3 clips,
0 lines, 3 visual segments.`) and then asked the agent a real question
("What coverage do we have of the S03 rooftop scene?") against the
freshly-copied, freshly-ingested checkout — got a correct answer sourced
from real ClickHouse data, following only what's written in this file.
