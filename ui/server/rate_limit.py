"""Per-session_id request throttling for /chat.

/chat is intentionally open to allUsers (see docs/SECURITY.md) with a
--max-instances cap but, until now, nothing stopped one session from
hammering the endpoint and starving everyone else on the same instance. A
token bucket per session_id is the smallest thing that fixes that: cheap,
no external dependency, good enough for a hackathon demo's traffic shape.

Same caveat as ui/server/agent_runner.py's _known_sessions: this state is
per-process, not shared across Cloud Run instances, and grows unbounded for
the life of the process. Acceptable for the same reason (short-lived demo
instances, session affinity already routes a session's requests to one
instance) -- not something to reach for in a longer-running deployment.
"""

import time
from collections import defaultdict

CAPACITY = 5
REFILL_SECONDS = 3.0  # one token every 3s -- a burst of 5, then ~20/min sustained


class _Bucket:
    __slots__ = ("tokens", "updated")

    def __init__(self) -> None:
        self.tokens = float(CAPACITY)
        self.updated = time.monotonic()


_buckets: dict[str, _Bucket] = defaultdict(_Bucket)


def allow(session_id: str) -> bool:
    """True if this session_id may make a request now, consuming a token if so."""
    bucket = _buckets[session_id]
    now = time.monotonic()
    elapsed = now - bucket.updated
    bucket.tokens = min(CAPACITY, bucket.tokens + elapsed / REFILL_SECONDS)
    bucket.updated = now

    if bucket.tokens >= 1:
        bucket.tokens -= 1
        return True
    return False


def retry_after(session_id: str) -> float:
    """Seconds until this session_id will next have a token available (0 if
    it already does), for a real `Retry-After` header instead of a made-up
    number. Read-only: unlike `allow()`, it doesn't consume a token or write
    back the refill, so calling it doesn't change when the wait actually
    ends. Only meaningful right after `allow()` returned False for the same
    session_id — the bucket may have refilled further by the time this runs.
    """
    bucket = _buckets[session_id]
    elapsed = time.monotonic() - bucket.updated
    projected_tokens = min(CAPACITY, bucket.tokens + elapsed / REFILL_SECONDS)
    if projected_tokens >= 1:
        return 0.0
    return (1 - projected_tokens) * REFILL_SECONDS
