# Architecture

## Data flow

```
raw clip (.mp4) --Gemini video analysis--> data/processed/*.json
                                                    |
                                          pipeline/embed.py (Gemini embeddings)
                                                    |
                                          pipeline/ingest.py
                                                    v
                                    ClickHouse: clips / dialogue / visuals
                                                    v
                                    agent/tools/*.py (search, coverage, takes)
                                                    v
                                          ADK agent (agent/agent.py)
```

`data/processed/*.json` and `data/manifest.json` (shoot metadata: scenes,
characters, character aliases) are committed to the repo — see README.md's
"Running it yourself" for why. `pipeline/ingest.py` reads both, embeds
dialogue/visual text, and truncates+reloads the three ClickHouse tables.
It's idempotent.

## The agent

`agent/agent.py` wires a Gemini model (via Google's Agent Development Kit)
to four tools in `agent/tools/`:

- **search_dialogue** / **search_visuals** — semantic search over
  ClickHouse-embedded dialogue lines / visual segment descriptions.
- **get_coverage** — per-scene gap analysis: which expected characters
  never appear in a scene's shots, using `data/manifest.json`'s
  `character_aliases` map to resolve Gemini's inconsistent naming before
  computing gaps.
- **compare_takes** — pulls all takes of a resolved scene/setup and diffs
  them (technical problems, timing).

`agent/prompts.py` instructs the agent to resolve an unnamed scene via
`search_dialogue` before ever asking a clarifying question, and to treat
`compare_takes` as a two-step operation (search first, then compare with
the resolved scene) rather than guessing scene identity from the query
text.

## Two deployment targets, not a migration

The agent runs two independent ways, deliberately, not as an in-progress
replacement of one by the other:

1. **In-process on Cloud Run (`dailies-ui`), the primary path.**
   `ui/server/agent_runner.py` imports `agent.agent.root_agent` directly
   and drives it with ADK's `InMemoryRunner`, streaming tool-call and
   response events to the browser over SSE (`ui/server/main.py`'s
   `/chat` endpoint). This is what's live at the demo URL. It scales to
   zero — no cost while idle — which Agent Engine does not.

2. **Vertex AI Agent Engine (`dailies-agent`), judging-day only.**
   A separately deployed, separately billed instance of the same agent
   code (`adk deploy agent_engine`, see `docs/RUNBOOK.md`), for judges or
   anyone who wants to query the agent directly without going through the
   UI. It does not scale to zero, so it's deployed shortly before judging
   and torn down immediately after — see RUNBOOK's "Teardown" section.

The two targets don't share a runner: Agent Engine's `stream_query` event
shape differs from `InMemoryRunner`'s, so `ui/server/agent_runner.py` and
the Agent Engine deploy path are separate code, not a shared abstraction
built for a single caller.

## UI

FastAPI backend (`ui/server/`) + React/Vite frontend (`ui/`), built into
one container — see `docs/UI.md` for the split and why the Docker build
context is the whole repo, not just `ui/`.

## Storage

- **ClickHouse** (Cloud, `schema/clickhouse.sql`) — the searchable index:
  `clips`, `dialogue`, `visuals` tables, embeddings included.
- **GCS** (`gs://dailies-room-dailies`) — the actual clip video files and
  contact-strip thumbnails. Never exposed directly to the browser; see
  `docs/UI.md` and `docs/SECURITY.md` for how playback URLs are signed.
- **Secret Manager** — `clickhouse-password`, read by
  `agent/config.py::ch_password()`, falling back to a local env var in
  dev (see `docs/RUNBOOK.md`'s "Secret rotation").
