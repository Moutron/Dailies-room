"""Runs tests/eval_cases.yaml against the local in-process agent.

Plain script rather than a pytest module: pytest's collection/import
machinery was observed to intermittently break google-genai's
GOOGLE_GENAI_USE_VERTEXAI env-var detection in this environment (plain
`python3` with the identical import order did not reproduce it — root
cause not pinned down, not worth more time chasing since it's a local
dev-loop quirk, not a deployed-agent issue). A plain script sidesteps it.

Usage: python tests/run_eval_cases.py
"""

import asyncio
import sys
from pathlib import Path

import yaml
from google.adk.runners import InMemoryRunner
from google.genai import types

from agent import config
from agent.agent import root_agent

CASES = yaml.safe_load((Path(__file__).parent / "eval_cases.yaml").read_text())
APP_NAME = "dailies-room-eval"


def _very_long_message() -> str:
    return "Please find every shot of the rooftop scene. " * 500  # ~23k chars


async def _run(query: str) -> str:
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    await runner.session_service.create_session(
        app_name=APP_NAME, user_id="eval", session_id="eval-session"
    )
    content = types.Content(role="user", parts=[types.Part(text=query)])
    text = ""
    async for event in runner.run_async(
        user_id="eval", session_id="eval-session", new_message=content
    ):
        if event.content and event.content.parts:
            text += "".join(p.text for p in event.content.parts if getattr(p, "text", None))
    return text


async def _run_case(case: dict) -> tuple[bool, str]:
    setup = case.get("setup")
    orig_ch_host = config.CH_HOST
    orig_ch_password = config.ch_password
    try:
        if setup == "clickhouse_unreachable":
            config.CH_HOST = "unreachable.invalid.test"
        elif setup == "clickhouse_wrong_password":
            config.ch_password = lambda: "definitely-wrong-password"

        query = _very_long_message() if case.get("generated") == "very_long" else case["query"]
        answer = await _run(query)
    finally:
        config.CH_HOST = orig_ch_host
        config.ch_password = orig_ch_password

    lower = answer.lower()
    failures = []
    must_mention = case.get("must_mention", [])
    if must_mention and not any(phrase.lower() in lower for phrase in must_mention):
        failures.append(f"expected at least one of {must_mention}")
    for phrase in case.get("must_not_mention", []):
        if phrase.lower() in lower:
            failures.append(f"unexpected {phrase!r}")

    return (not failures, f"{answer[:300]!r}" + (f"  FAILURES: {failures}" if failures else ""))


async def main() -> int:
    all_ok = True
    for case in CASES:
        ok, detail = await _run_case(case)
        all_ok &= ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case['name']}: {detail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
