# Agent quality

## Eval cases (`tests/eval_cases.yaml`, run by `tests/run_eval_cases.py`)

A plain script, not a pytest module: pytest's collection/import machinery
was observed to intermittently break `google-genai`'s
`GOOGLE_GENAI_USE_VERTEXAI` env-var detection in this environment (plain
`python3` with the identical import order did not reproduce it — root
cause not pinned down, not worth chasing further since it's a local
dev-loop quirk, not a deployed-agent issue). Run it with:

```bash
source .venv/bin/activate
python tests/run_eval_cases.py
```

Each case sends a real query through `InMemoryRunner` against the real
(committed) ClickHouse-backed index and asserts on substrings in the
agent's final answer — `must_mention` (at least one phrase must appear)
and `must_not_mention` (none may appear). Cases:

- **finds_hand_line** — a real, findable dialogue line resolves to an
  answer containing a timecode.
- **resolves_line_without_asking_scene** — the agent must resolve scene
  via `search_dialogue` itself rather than asking "which scene?" when the
  query doesn't name one (see `agent/prompts.py`).
- **honest_when_absent** — asking about footage that doesn't exist (a
  horse) gets an honest "no"/"can't find," never a fabricated timecode.
- **surfaces_technical_problems** — the agent surfaces real flagged
  issues (focus, boom, audio) when asked broadly about problems.
- **honest_when_index_down** / **wrong_clickhouse_password** — simulated
  ClickHouse failures (unreachable host, bad credentials) must produce an
  honest "unable"/"unreachable" answer, not a hang or a guess. Both hit
  the same `@reports_index_errors` path — the eval doesn't currently
  distinguish "can't connect" from "wrong password" in the agent's
  response, which is a known gap, not an oversight.
- **nonsense_question** — gibberish input never produces a fabricated
  timecode.
- **very_long_message** — a ~23k-character generated message (matching
  real S03 data, so timecodes in the answer are legitimate) — the
  pass/fail signal here is the runner completing without crashing or
  hanging, not content assertions.

## Resilience pass: honesty over helpfulness

Every tool failure — dead ClickHouse, wrong password, no matching
footage — is designed to surface as a clear "I can't find that" / "the
index is unreachable," never a fabricated answer. This is enforced by
`agent/tools/_errors.py`'s `@reports_index_errors` decorator (catches
ClickHouse client exceptions and returns a typed error the agent is
prompted to relay honestly) and exercised by the eval cases above. See
`agent/prompts.py` for the honesty instructions given to the model
directly.

## Unit tests

`tests/` also has ordinary pytest coverage for the pipeline and tool
modules (schema resolution, coverage gap computation, timecode math,
etc.) — run with `python -m pytest -q` after activating `.venv`. These
test individual functions in isolation; `run_eval_cases.py` is the only
end-to-end check of actual agent behavior against a live model and a
live index.
