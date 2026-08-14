"""Tests for ui/server/agent_runner.py's ADK-event-to-SSE translation.

The real InMemoryRunner is left in place (its construction doesn't touch the
network) but `run_async` and session creation are mocked so no real Gemini
call happens.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.events.event import Event
from google.genai import types

from ui.server.agent_runner import stream_chat


def _text_event(text: str, final: bool = True) -> Event:
    content = types.Content(role="model", parts=[types.Part(text=text)])
    return Event(author="dailies_room", content=content, turn_complete=final)


def _tool_call_event(tool: str, args: dict) -> Event:
    part = types.Part(function_call=types.FunctionCall(name=tool, args=args))
    content = types.Content(role="model", parts=[part])
    return Event(author="dailies_room", content=content)


def _tool_result_event(tool: str, response: dict, call_id: str | None = None) -> Event:
    part = types.Part(
        function_response=types.FunctionResponse(name=tool, response=response, id=call_id)
    )
    content = types.Content(role="model", parts=[part])
    return Event(author="dailies_room", content=content)


async def _fake_events(*events):
    for e in events:
        yield e


def _parse_sse(text: str) -> list[dict]:
    frames = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event_type, data = None, None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        frames.append({"type": event_type, **(data or {})})
    return frames


@pytest.mark.asyncio
async def test_stream_chat_emits_tool_call_result_and_message():
    events = [
        _tool_call_event("search_dialogue", {"query": "hello"}),
        _tool_result_event("search_dialogue", {"result": [{"clip_id": "c1"}]}),
        _text_event("Found one line."),
    ]
    with (
        patch("ui.server.agent_runner._runner.session_service.create_session", new=AsyncMock()),
        patch("ui.server.agent_runner._runner.run_async", return_value=_fake_events(*events)),
    ):
        chunks = [chunk async for chunk in stream_chat("hello", "session-1")]

    frames = _parse_sse("".join(chunks))
    types_seen = [f["type"] for f in frames]

    assert types_seen == ["tool_call", "tool_result", "message", "done"]
    assert frames[0]["tool"] == "search_dialogue"
    assert frames[0]["args"] == {"query": "hello"}
    assert frames[1]["result"] == {"result": [{"clip_id": "c1"}]}
    assert frames[2]["text"] == "Found one line."


@pytest.mark.asyncio
async def test_stream_chat_emits_tool_evidence_when_the_tool_call_recorded_it():
    from agent.tools import _evidence

    _evidence._by_call_id.clear()
    _evidence._record(
        "call-abc",
        _evidence.QueryEvidence(table="dialogue", sql="SELECT 1", elapsed_ms=1.2, row_count=3),
    )
    events = [
        _tool_call_event("search_dialogue", {"query": "hello"}),
        _tool_result_event("search_dialogue", {"result": [{"clip_id": "c1"}]}, call_id="call-abc"),
        _text_event("Found one line."),
    ]
    with (
        patch("ui.server.agent_runner._runner.session_service.create_session", new=AsyncMock()),
        patch("ui.server.agent_runner._runner.run_async", return_value=_fake_events(*events)),
    ):
        chunks = [chunk async for chunk in stream_chat("hello", "session-evidence")]

    frames = _parse_sse("".join(chunks))
    types_seen = [f["type"] for f in frames]

    assert types_seen == ["tool_call", "tool_result", "tool_evidence", "message", "done"]
    evidence_frame = frames[2]
    assert evidence_frame["tool"] == "search_dialogue"
    assert evidence_frame["queries"] == [
        {"table": "dialogue", "sql": "SELECT 1", "elapsed_ms": 1.2, "row_count": 3}
    ]
    # Popped, not re-served on a later turn.
    assert _evidence._by_call_id == {}


@pytest.mark.asyncio
async def test_stream_chat_emits_no_tool_evidence_when_none_was_recorded():
    events = [
        _tool_call_event("search_dialogue", {"query": "hello"}),
        _tool_result_event("search_dialogue", {"result": [{"clip_id": "c1"}]}),
    ]
    with (
        patch("ui.server.agent_runner._runner.session_service.create_session", new=AsyncMock()),
        patch("ui.server.agent_runner._runner.run_async", return_value=_fake_events(*events)),
    ):
        chunks = [chunk async for chunk in stream_chat("hello", "session-no-evidence")]

    frames = _parse_sse("".join(chunks))
    assert "tool_evidence" not in [f["type"] for f in frames]


@pytest.mark.asyncio
async def test_stream_chat_reuses_session_on_second_call():
    with (
        patch(
            "ui.server.agent_runner._runner.session_service.create_session", new=AsyncMock()
        ) as mock_create,
        patch("ui.server.agent_runner._runner.run_async", return_value=_fake_events()),
    ):
        [chunk async for chunk in stream_chat("first", "session-reuse")]
        [chunk async for chunk in stream_chat("second", "session-reuse")]

    assert mock_create.await_count == 1


@pytest.mark.asyncio
async def test_stream_chat_reports_real_turn_count_from_session_history():
    """`done`'s turn_count comes from the real ADK session history (user-
    authored events), not the request count — it's the only honest signal
    the client has that Cloud Run session affinity silently reset a session
    under the same id (docs/SECURITY.md)."""
    session = MagicMock()
    session.events = [
        Event(author="user", content=types.Content(role="user", parts=[types.Part(text="hi")])),
        Event(
            author="dailies_room",
            content=types.Content(role="model", parts=[types.Part(text="hello")]),
        ),
        Event(author="user", content=types.Content(role="user", parts=[types.Part(text="again")])),
    ]
    with (
        patch("ui.server.agent_runner._runner.session_service.create_session", new=AsyncMock()),
        patch(
            "ui.server.agent_runner._runner.session_service.get_session",
            new=AsyncMock(return_value=session),
        ),
        patch("ui.server.agent_runner._runner.run_async", return_value=_fake_events()),
    ):
        chunks = [chunk async for chunk in stream_chat("hello", "session-turns")]

    frames = _parse_sse("".join(chunks))
    assert frames[-1] == {"type": "done", "turn_count": 2}


@pytest.mark.asyncio
async def test_stream_chat_reports_zero_turn_count_when_session_is_missing():
    with (
        patch("ui.server.agent_runner._runner.session_service.create_session", new=AsyncMock()),
        patch(
            "ui.server.agent_runner._runner.session_service.get_session",
            new=AsyncMock(return_value=None),
        ),
        patch("ui.server.agent_runner._runner.run_async", return_value=_fake_events()),
    ):
        chunks = [chunk async for chunk in stream_chat("hello", "session-missing")]

    frames = _parse_sse("".join(chunks))
    assert frames[-1] == {"type": "done", "turn_count": 0}


@pytest.mark.asyncio
async def test_stream_chat_turns_run_async_exception_into_error_event():
    async def broken(*args, **kwargs):
        raise RuntimeError("model unavailable")
        yield  # pragma: no cover - makes this an async generator

    with (
        patch("ui.server.agent_runner._runner.session_service.create_session", new=AsyncMock()),
        patch("ui.server.agent_runner._runner.run_async", side_effect=broken),
    ):
        chunks = [chunk async for chunk in stream_chat("hello", "session-err")]

    frames = _parse_sse("".join(chunks))

    assert frames[0]["type"] == "error"
    assert "RuntimeError" in frames[0]["message"]
    assert not any(f["type"] == "done" for f in frames)
