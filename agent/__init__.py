"""Package init — configures structured JSON logging before any tool logs.

Cloud Logging (Cloud Run and Agent Engine both) auto-promotes a stdout/
stderr line to a structured jsonPayload when the line is valid JSON, with
`severity` read from a top-level key. Stdlib `logging` has no handler
attached by default in either runtime, and even with one, fields passed
via `extra={...}` don't reach the log line unless the formatter emits
them — hence the custom formatter instead of `logging.basicConfig`.
"""

import json
import logging

_STANDARD_LOG_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        payload.update(
            {k: v for k, v in record.__dict__.items() if k not in _STANDARD_LOG_RECORD_ATTRS}
        )
        return json.dumps(payload, default=str)


_agent_logger = logging.getLogger("agent")
if not _agent_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(_JSONFormatter())
    _agent_logger.addHandler(_handler)
    _agent_logger.setLevel(logging.INFO)
    _agent_logger.propagate = False
