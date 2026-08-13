# UI

FastAPI backend (`ui/server/`) + React/Vite frontend (`ui/src/`, not
covered in detail here — see the source), built into a single container
and served from one FastAPI app.

## Backend surface (`ui/server/main.py`)

- `POST /chat` — streams the agent's reply as SSE (`text/event-stream`),
  including which tools it called, via `ui/server/agent_runner.py`'s
  `stream_chat()`.
- `GET /clip/{clip_id}/url` — a short-lived signed GCS playback URL.
- `GET /clip/{clip_id}/thumbnails` — contact-strip frame list for a clip.
- `GET /thumbs/{filename}` — serves a single thumbnail JPEG from
  `data/thumbs/`.
- `GET /health` — liveness check.
- Everything else falls through to the built frontend (`ui/dist/`,
  mounted as static files) if present.

In dev, Vite's dev server (port 5173) proxies `/chat`, `/clip`, `/thumbs`,
`/health` to the FastAPI backend on 8001 (`ui/vite.config.ts`), so every
request is same-origin in both dev and production — no CORS middleware
needed either way.

## Clip playback (`ui/server/clips.py`)

The GCS bucket (`agent.config.GCS_BUCKET`) has no public/`allUsers`
binding, so the browser never talks to GCS directly. Every playback URL
is a short-lived (15 minute) V4 signed URL minted server-side and handed
to the `<video>` element.

Signing goes through the IAM `signBlob` API, impersonating the service
account named by the `GCS_SIGNER_SA` env var, which must hold
`roles/iam.serviceAccountTokenCreator` on itself — this works both for a
local user's `gcloud auth application-default login` credentials (which
have no private key to sign with directly) and for Cloud Run's runtime
service account. See `docs/SECURITY.md` for the exact grant.

Thumbnails are pre-extracted offline at a fixed 0.5 fps starting at
`t=0` (`data/thumbs/`), so a frame's timestamp is derived from its
position in the sorted filename list, not probed per-file.

## Build (`Dockerfile`)

Two stages: `node:20-slim` builds the Vite frontend into `ui/dist/`;
`python:3.12-slim` installs the backend and copies the built frontend in.

Deployed with `gcloud run deploy dailies-ui --source .` from the **repo
root**, not `ui/`, because the backend imports `agent/`, `pipeline/`, and
`schema/` from the repo root (e.g. `from agent.agent import root_agent`)
— the build context has to include all of them, not just `ui/`. This is a
deliberate deviation from what a UI-only Dockerfile might suggest, not an
oversight.

`data/manifest.json` and `data/thumbs/` are explicitly `COPY`'d into the
image — the former because `agent/tools/coverage.py` reads it from disk
at request time to resolve character aliases; omitting it doesn't fail
loudly, it makes `get_coverage` report the footage index as "unreachable"
(see `agent/tools/_errors.py`), which cost real debugging time once
already (see README.md's deploy-regression note).
