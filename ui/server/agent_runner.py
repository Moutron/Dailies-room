"""Wraps root_agent in an InMemoryRunner and turns its event stream into SSE.

Each ADK `Event` can carry a function call, a function response, and/or text
in the same turn. We forward all three kinds as distinct SSE event types so
the frontend can render the tool trace (8.5's ToolTrace) as it happens rather
than only after the final answer lands.
"""

import json
from collections.abc import AsyncIterator

from google.adk.runners import InMemoryRunner
from google.genai import types

from agent.agent import root_agent

APP_NAME = "dailies-room"

_runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
# Per-process only -- not shared across Cloud Run instances. See
# docs/SECURITY.md's "Session state is in-process, not shared across
# instances" for why this matters and how it's mitigated (session affinity).
_known_sessions: set[str] = set()


def _sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def _ensure_session(session_id: str) -> None:
    if session_id in _known_sessions:
        return
    await _runner.session_service.create_session(
        app_name=APP_NAME, user_id="director", session_id=session_id
    )
    _known_sessions.add(session_id)


async def stream_chat(message: str, session_id: str) -> AsyncIterator[str]:
    """Run one turn and yield SSE-formatted chunks: tool_call, tool_result, message, done, error."""
    await _ensure_session(session_id)
    content = types.Content(role="user", parts=[types.Part(text=message)])

    try:
        async for event in _runner.run_async(
            user_id="director", session_id=session_id, new_message=content
        ):
            for call in event.get_function_calls():
                yield _sse("tool_call", {"tool": call.name, "args": call.args or {}})

            for resp in event.get_function_responses():
                yield _sse("tool_result", {"tool": resp.name, "result": resp.response})

            if event.content and event.content.parts:
                text = "".join(p.text for p in event.content.parts if getattr(p, "text", None))
                if text:
                    yield _sse("message", {"text": text, "final": event.is_final_response()})
    except Exception as exc:  # noqa: BLE001 — surface to the UI, don't crash the stream
        yield _sse("error", {"message": f"The agent failed to respond ({exc.__class__.__name__})."})
        return

    yield _sse("done", {})
