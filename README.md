# The Dailies Room

> Ask your footage a question. Compare takes of a line. Find the coverage
> you're missing — before the location is struck.

Agentic Cinema Hackathon · Gemini + ADK + ClickHouse

## The problem

On a shoot, dailies review means someone — usually the editor or the
director — scrubbing through raw footage by hand to answer questions like
"do we have a clean take of that line," "did we ever get a close-up on
him," or "which take had the boom in frame." That's slow, and it doesn't
scale past a couple of takes per setup. The Dailies Room answers those
questions directly: ask in plain language, get an answer grounded in what
was actually shot, with a timecode and a playable clip, not a guess.

## What it does

An agent (Gemini + Google's Agent Development Kit) with four tools —
semantic dialogue search, semantic visual search, per-scene coverage and
gap analysis, and take comparison — backed by a ClickHouse index of
Gemini's own video analysis of every clip. Ask "find the shot with the
newspaper headline," "any takes with technical problems," or "which take
of the rooftop setup has the fewest problems" and it searches the real
index, not a script. It's built to be honest when the footage isn't
there: no character named Celia in this dataset gets "I can't find that,"
not a fabricated close-up.

## Architecture

Ingest pipeline (Gemini analyzes each clip → structured JSON → embedded →
loaded into ClickHouse) feeds an ADK agent exposing four tools, served two
ways: embedded in-process inside a Cloud Run UI service (the primary path
— see `ui/`), and independently on Vertex AI Agent Engine for direct
querying (see `docs/RUNBOOK.md`). Full write-up, including why those two
deployment targets exist side by side instead of one replacing the other,
in `docs/ARCHITECTURE.md`. Security posture and IAM audit in
`docs/SECURITY.md`; agent behavior testing in `docs/AGENT_QUALITY.md`; UI
design notes in `docs/UI.md`.

## Demo

See `docs/RUNBOOK.md` for how to run it live. A recorded walkthrough is
linked from the submission (Phase 10 — this repo doesn't embed video).

## Running it yourself

**This is meant to actually work from a clone, not just look like it
does.** `data/processed/` (Gemini's video analysis output) and
`data/manifest.json` are committed to the repo, so you don't need to pay
for video analysis to get a working index — clone, ingest, done, in
minutes.

Full instructions — prerequisites, local setup, rebuilding the index from
the committed data, deploying both services, secret rotation, and
teardown — are in **[`docs/RUNBOOK.md`](docs/RUNBOOK.md)**, verified by
actually cloning into a fresh directory and following it literally (see
that file's "Clean-clone verification" section for what that caught).

## Design decisions

Notable, possibly-surprising calls, with the reasoning behind them:

- **Two independent deployment targets, not a migration** — the UI's
  agent runner stays in-process on Cloud Run; Agent Engine is judging-day
  infrastructure only, torn down after and redeployed fresh before
  demoing, because it doesn't scale to zero the way Cloud Run does. See
  `docs/ARCHITECTURE.md`.
- **Honesty over helpfulness** — every tool failure (dead ClickHouse,
  wrong password, no matching footage) surfaces as a clear "I can't find
  that" / "the index is unreachable," never a fabricated answer. See
  `docs/AGENT_QUALITY.md`'s resilience pass.
- **`data/processed/` committed on purpose** — the alternative
  (regenerating it) means nobody but the author can afford to actually
  run this project. See "Running it yourself" above.
- **Dedicated, least-privilege service accounts per deployment** rather
  than reusing broad default credentials — see `docs/SECURITY.md`,
  including the one deliberate broader-than-necessary grant that's
  documented rather than silently carried.

## Attribution

Uses footage from *Tears of Steel* (Blender Foundation, CC-BY) — full
details in [`ATTRIBUTION.md`](ATTRIBUTION.md).

## License

Apache 2.0 — see [`LICENSE`](LICENSE).
