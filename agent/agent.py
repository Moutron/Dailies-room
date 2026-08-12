"""The Dailies Room — root agent."""

from google.adk import Agent
from google.adk.models.google_llm import Gemini

from agent import config
from agent.prompts import ROOT_INSTRUCTION
from agent.tools.coverage import get_coverage
from agent.tools.search import search_dialogue, search_visuals
from agent.tools.takes import compare_takes

# Pass vertexai/project/location explicitly rather than relying on
# GOOGLE_GENAI_USE_VERTEXAI/GOOGLE_CLOUD_PROJECT/GOOGLE_CLOUD_LOCATION
# env-var auto-detection inside google-genai's Client — that detection was
# observed to be intermittently flaky in local dev (same env vars, same
# process, sometimes not picked up; root cause not pinned down). Being
# explicit here removes the dependency on it entirely.
_model = Gemini(
    model=config.AGENT_MODEL,
    client_kwargs={"vertexai": True, "project": config.PROJECT_ID, "location": config.LOCATION},
)

root_agent = Agent(
    name="dailies_room",
    model=_model,
    description=(
        "Answers questions about raw footage from a film shoot — what was "
        "said, what was shot, and which takes are worth watching."
    ),
    instruction=ROOT_INSTRUCTION,
    tools=[search_dialogue, search_visuals, get_coverage, compare_takes],
)
