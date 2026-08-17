# Security

## Service accounts

Two deployments, two dedicated service accounts, each granted only the
roles the code actually calls:

### `dailies-ui@dailies-room.iam.gserviceaccount.com` — Cloud Run runtime

| Role | Why |
|---|---|
| `roles/aiplatform.user` | Gemini calls (video understanding at ingest time; agent reasoning and embeddings at query time) via Vertex AI. |
| `roles/secretmanager.secretAccessor` (scoped to the `clickhouse-password` secret, not project-wide) | `agent/config.py::ch_password()`'s Secret Manager fallback. |
| `roles/storage.objectViewer` (scoped to `gs://dailies-room-dailies`, not project-wide) | Reading clip video and thumbnails for playback. |
| `roles/iam.serviceAccountTokenCreator` (on itself) | Signing short-lived V4 GCS playback URLs via the IAM `signBlob` API — see `docs/UI.md`'s "Clip playback" section for why this indirection is needed instead of signing directly. |

Deployed with `--service-account=dailies-ui@dailies-room.iam.gserviceaccount.com`.

**Not yet granted:** `POST /ingest/upload` (`ui/server/upload.py`) writes
an uploaded clip's mp4 and poster to `gs://dailies-room-dailies` via
`ui/server/clips.py::upload_blob()`, but the table above only grants
`roles/storage.objectViewer` (read-only) — confirmed, not assumed, by
reading this table. Uploads will fail on the GCS write step until the
runtime SA also gets `roles/storage.objectCreator` (scoped to the same
bucket, not project-wide, matching how `objectViewer` is scoped above):

```bash
gsutil iam ch \
  serviceAccount:dailies-ui@dailies-room.iam.gserviceaccount.com:objectCreator \
  gs://dailies-room-dailies
```

Run this (or the equivalent `gcloud storage buckets add-iam-policy-binding`)
before relying on uploads in a live deployment — it has not been run as
part of this change.

### `dailies-agent@dailies-room.iam.gserviceaccount.com` — Vertex AI Agent Engine

Judging-day only (see `docs/ARCHITECTURE.md`). Same shape, plus the three
roles Agent Engine's own infrastructure requires:

| Role | Why |
|---|---|
| `roles/aiplatform.user` | Same as above. |
| `roles/secretmanager.secretAccessor` (on `clickhouse-password`) | Same as above. |
| `roles/storage.objectViewer` (on `gs://dailies-room-dailies`) | Same as above — though this path doesn't serve signed playback URLs itself. |
| `roles/logging.logWriter`, `roles/cloudtrace.agent`, `roles/monitoring.metricWriter` | Required by the Agent Engine runtime itself for its managed logging/tracing/metrics, not by application code. |

Exact grant commands for both are in `docs/RUNBOOK.md`.

## One documented broader-than-necessary grant

The Compute Engine default service account
(`766122679114-compute@developer.gserviceaccount.com`) still holds a
**project-level** `roles/storage.objectViewer` grant, left in place
deliberately rather than removed. It predates the `dailies-ui` SA and is
needed for Cloud Build's source-tarball read during `gcloud run deploy
--source .` — the build step runs under this project's default Cloud
Build identity, which is separate from the `--service-account` used by
the deployed *runtime* revision, so scoping the runtime SA down does not
touch this grant. It is not used by any application code path (neither
`ui/server/` nor `agent/` runs as this SA anymore) — it exists solely to
let the deploy command itself read the uploaded source. Narrowing this
further (e.g. a bucket-scoped grant on Cloud Build's staging bucket
instead of project-wide) was judged not worth the risk of breaking the
deploy command this close to submission; noted here rather than silently
carried.

## GCS access

`gs://dailies-room-dailies` has no `allUsers`/public binding. The browser
never talks to GCS directly — every clip playback URL is a 15-minute
signed URL minted server-side (`ui/server/clips.py`). See `docs/UI.md`.

## `/chat` is intentionally unauthenticated

Cloud Run's `dailies-ui` service grants `roles/run.invoker` to
`allUsers` — anyone with the URL can use the chat endpoint, with no
login or API key. This is a deliberate choice for a
hackathon demo (judges need to hit the live URL with zero setup), not an
oversight, but it is a real gap for anything beyond a demo:

- No per-user auth or session isolation beyond a client-generated
  `session_id` (see `ui/server/agent_runner.py`).
- The Cloud Run service is capped at `--max-instances=3` (set via
  `gcloud run services update`), so a burst of traffic can no longer scale
  the service — and the underlying Gemini/ClickHouse calls with it —
  without bound; it now caps out at 3 concurrent instances, still bounded
  further by whatever quota/budget alerts are in place (see
  `docs/RUNBOOK.md`'s teardown section for the budget alert).
- `/chat` now rate-limits per `session_id` (`ui/server/rate_limit.py`): a
  5-request burst, refilling at 1 request/3s (~20/min sustained), returning
  HTTP 429 past that. It's a per-process in-memory token bucket, same
  caveat as `_known_sessions` below — not shared across instances, unbounded
  growth for the life of the process — acceptable for a demo, not for a
  longer-running deployment. It does not stop a client from rotating
  `session_id` values to dodge the limit; that requires real per-user auth.

Before running this beyond a demo: put `/chat` behind real auth (the
`max-instances` cap and per-session rate limiting are done, but neither
stops a determined client with many session IDs).

## `/ingest/upload` is also intentionally unauthenticated, with tighter caps

Same tradeoff as `/chat`, same `allUsers` `roles/run.invoker` binding — no
login required, deliberate for a hackathon demo. It costs more per request
than `/chat` (one real Gemini video-analysis call plus an embed call per
upload, not just a chat turn), so it is capped harder:

- A separate, stricter rate-limit bucket (`ui/server/rate_limit.py`'s
  `namespace` param) — `UPLOAD_RATE_CAPACITY=2` requests, refilling at
  1/60s, independent of `/chat`'s bucket for the same `session_id`. Same
  per-process, not-shared-across-instances, unbounded-growth caveat as
  `/chat`'s bucket.
- `MAX_UPLOAD_BYTES` (30 MiB, under Cloud Run's 32 MiB HTTP/1 request-body
  cap) and `MAX_FRAMES` (300) bound the size of any single request.
- `clip_id` is validated against `^[a-z0-9_]{1,64}$` before it is ever used
  to build a GCS blob path, so a request can't write outside
  `clips/`/`posters/` in the bucket.

**Residual cost exposure, not fully mitigated:** the rate limit is
per-`session_id`, and `session_id` is client-generated and freely
rotatable — the same gap `/chat`'s section above already documents. A
client rotating session IDs can still drive real Gemini + embedding
spend, one call per accepted upload, up to whatever `--max-instances`
and budget alerts allow. Before running this beyond a demo: real
per-user auth, same as `/chat`.

## Session state is in-process, not shared across instances

`ui/server/agent_runner.py` uses ADK's `InMemoryRunner`, whose
`InMemorySessionService` keeps every session's conversation state in that
process's own memory — nothing is persisted to a shared store. With
`--max-instances=3`, if a browser's two requests for the same
client-generated `session_id` land on *different* Cloud Run instances, the
second instance has never seen that session: `InMemorySessionService`
would either silently start a fresh, empty session (losing all prior
conversation context with no error) or, worse, later raise
`AlreadyExistsError` if `_known_sessions` ever got out of sync with what a
given instance actually holds. This is not a theoretical concern — it's
the direct consequence of per-process in-memory state behind a
multi-instance load balancer.

Mitigated (not fixed) via `gcloud run services update dailies-ui
--session-affinity`, which routes a given client's requests to the same
instance for the life of that instance. This does not help across
instance restarts, scale-to-zero, or a scale-down event, and there's no
retry/fallback if the sticky instance is gone — for a hackathon demo
session (single sitting, one instance, no scale-down mid-demo) that's an
acceptable bet given the alternative (a shared session store — Firestore,
Redis) is real architecture work, not a quick fix. Before running this
beyond a demo: move to a shared, persistent session store so conversation
continuity doesn't depend on routing luck.

## Secrets

`clickhouse-password` lives in Secret Manager, never in the repo or in
committed `.env` files. `.env.example`'s `CLICKHOUSE_PASSWORD` line is
intentionally left blank with the comment on its own line (see
`docs/RUNBOOK.md`'s clean-clone finding #4 for why inline comments there
are dangerous with `python-dotenv`). Rotation procedure is in
`docs/RUNBOOK.md`.
