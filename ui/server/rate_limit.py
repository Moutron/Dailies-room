"""Per-session_id request throttling for /chat and /ingest/upload.

/chat is intentionally open to allUsers (see docs/SECURITY.md) with a
--max-instances cap but, until now, nothing stopped one session from
hammering the endpoint and starving everyone else on the same instance. A
token bucket per session_id is the smallest thing that fixes that: cheap,
no external dependency, good enough for a hackathon demo's traffic shape.

/ingest/upload reuses the same mechanism through an optional `namespace`,
so an upload session's stricter bucket is tracked independently of that
same session's /chat bucket -- one Gemini video call + embed call per
upload is far more expensive than a /chat turn, so it gets its own,
tighter capacity/refill without touching /chat's.

Same caveat as ui/server/agent_runner.py's _known_sessions: this state is
per-process, not shared across Cloud Run instances, and grows unbounded for
the life of the process. Acceptable for the same reason (short-lived demo
instances, session affinity already routes a session's requests to one
instance) -- not something to reach for in a longer-running deployment.
"""

import time

CAPACITY = 5
REFILL_SECONDS = 3.0  # one token every 3s -- a burst of 5, then ~20/min sustained


class _Bucket:
    __slots__ = ("capacity", "refill_seconds", "tokens", "updated")

    def __init__(self, capacity: float, refill_seconds: float) -> None:
        self.tokens = float(capacity)
        self.updated = time.monotonic()
        self.capacity = capacity
        self.refill_seconds = refill_seconds


# The default (/chat) namespace's buckets live directly in this dict, keyed
# by bare session_id -- unchanged from before namespaces existed, so /chat's
# behaviour (and the tests that poke `_buckets[session_id]` directly) stays
# byte-identical. Other namespaces (e.g. "upload") get their own sub-dict.
_buckets: dict[str, _Bucket] = {}
_namespaced_buckets: dict[str, dict[str, _Bucket]] = {}


def _store(namespace: str | None) -> dict[str, _Bucket]:
    if namespace is None:
        return _buckets
    return _namespaced_buckets.setdefault(namespace, {})


def allow(
    session_id: str,
    namespace: str | None = None,
    capacity: float = CAPACITY,
    refill_seconds: float = REFILL_SECONDS,
) -> bool:
    """True if this session_id may make a request now, consuming a token if so."""
    store = _store(namespace)
    bucket = store.get(session_id)
    if bucket is None:
        bucket = _Bucket(capacity, refill_seconds)
        store[session_id] = bucket

    now = time.monotonic()
    elapsed = now - bucket.updated
    bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed / bucket.refill_seconds)
    bucket.updated = now

    if bucket.tokens >= 1:
        bucket.tokens -= 1
        return True
    return False


def retry_after(
    session_id: str,
    namespace: str | None = None,
    capacity: float = CAPACITY,
    refill_seconds: float = REFILL_SECONDS,
) -> float:
    """Seconds until this session_id will next have a token available (0 if
    it already does), for a real `Retry-After` header instead of a made-up
    number. Read-only: unlike `allow()`, it doesn't consume a token or write
    back the refill, so calling it doesn't change when the wait actually
    ends. Only meaningful right after `allow()` returned False for the same
    session_id — the bucket may have refilled further by the time this runs.
    """
    bucket = _store(namespace).get(session_id)
    if bucket is None:
        return 0.0
    elapsed = time.monotonic() - bucket.updated
    projected_tokens = min(bucket.capacity, bucket.tokens + elapsed / bucket.refill_seconds)
    if projected_tokens >= 1:
        return 0.0
    return (1 - projected_tokens) * bucket.refill_seconds
