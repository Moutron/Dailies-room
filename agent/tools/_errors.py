"""Turn a dead index into a tool result the model can react to, not a crash.

Without this, a ClickHouse connection failure raises out of the tool call
and aborts the whole agent run — the model never gets a turn to tell the
user the index is unreachable, it just dies. Catching here keeps that
honesty behavior a prompt instruction can actually act on.
"""

import functools


def reports_index_errors(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — any ClickHouse/network failure must become a result, not a crash
            return [{"error": f"The footage index is unreachable ({exc.__class__.__name__})."}]

    return wrapper
