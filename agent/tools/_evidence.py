"""Per-tool-call query evidence: table(s) touched, row count, elapsed ms, and
the rendered SQL.

Captured here, at the query call site, rather than reconstructed afterwards —
the UI's evidence row is the whole credibility argument for the product, so
it has to be the query that actually ran, not a guess at what it might have
been. Correlated to a specific model turn's tool call via `tool_context.
function_call_id` (ADK injects `tool_context` into any tool function that
declares it), which `ui/server/agent_runner.py` reads back off the matching
`FunctionResponse.id` to emit a `tool_evidence` SSE event.

A query that fails still gets an evidence entry — a ClickHouse outage is
itself something the "how did you know that" evidence row should be able to
account for, rather than silently omitting it and leaving the failed answer
with no evidence at all. `run_query` re-raises after recording, so
`agent/tools/_errors.py`'s `reports_index_errors` still turns it into the
error row the model sees.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from clickhouse_connect.driver.binding import finalize_query

# Embedding vectors are ~3000 floats — rendering one inline would make the
# evidence SQL unreadable and defeat the point of showing it. Every other
# parameter renders as its real, final value; only vectors get a placeholder.
_VECTOR_PARAM_NAMES = frozenset({"vec"})


@dataclass(frozen=True)
class QueryEvidence:
    table: str
    sql: str
    elapsed_ms: float
    row_count: int | None = None
    error: str | None = None


_by_call_id: dict[str, list[QueryEvidence]] = {}


def _display_params(params: dict) -> dict:
    return {
        k: (
            f"<embedding vector, {len(v)} dims>"
            if k in _VECTOR_PARAM_NAMES and isinstance(v, list)
            else v
        )
        for k, v in params.items()
    }


def _record(call_id: str | None, evidence: QueryEvidence) -> None:
    if call_id is not None:
        _by_call_id.setdefault(call_id, []).append(evidence)


def run_query(client, call_id: str | None, table: str, sql: str, params: dict):
    """Runs `sql` via `client`, timing it and — when `call_id` is given —
    recording the evidence for later pickup. Returns clickhouse-connect's
    QueryResult unchanged. Re-raises on failure, after recording an evidence
    entry that carries the error instead of a row count."""
    rendered_sql = finalize_query(sql, _display_params(params))
    start = time.perf_counter()
    try:
        result = client.query(sql, parameters=params)
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        _record(
            call_id,
            QueryEvidence(table=table, sql=rendered_sql, elapsed_ms=elapsed_ms, error=str(exc)),
        )
        raise
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    _record(
        call_id,
        QueryEvidence(
            table=table,
            sql=rendered_sql,
            elapsed_ms=elapsed_ms,
            row_count=len(result.result_rows),
        ),
    )
    return result


def pop(call_id: str | None) -> list[dict]:
    """Pops and serializes the evidence recorded for one tool call. Safe to
    call for a call_id with no evidence (e.g. a tool that hit an error path
    before ever building a query) — returns []."""
    if call_id is None:
        return []
    records = _by_call_id.pop(call_id, [])
    return [
        {
            k: v
            for k, v in (
                ("table", r.table),
                ("row_count", r.row_count),
                ("elapsed_ms", r.elapsed_ms),
                ("sql", r.sql),
                ("error", r.error),
            )
            if v is not None
        }
        for r in records
    ]
