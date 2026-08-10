"""Generate embeddings for dialogue and visual segments."""

from google import genai

from agent import config

EMBED_MODEL = "gemini-embedding-001"  # text-embedding-004 was deprecated 2026-01-14


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings.

    gemini-embedding-001 accepts exactly one text per request (unlike the
    old text-embedding-004, which took up to five) -- so "batch" here just
    means "the entry point that loops," not a single multi-text call.
    """
    client = genai.Client(vertexai=True, project=config.PROJECT_ID, location=config.LOCATION)
    return [
        client.models.embed_content(model=EMBED_MODEL, contents=text).embeddings[0].values
        for text in texts
    ]


def dialogue_text(seg: dict) -> str:
    """What we embed for a line of dialogue.

    Includes delivery, not just words — so "find the angry version of this
    line" can match on performance, which is the point of reviewing dailies.
    """
    return f"{seg['speaker']}: {seg['text']} (delivered: {seg['delivery']})"


def visual_text(seg: dict) -> str:
    """What we embed for a visual beat."""
    parts = [seg["description"], f"shot type: {seg['shot_type']}"]
    if seg.get("characters_visible"):
        parts.append("featuring " + ", ".join(seg["characters_visible"]))
    if seg.get("notable_elements"):
        parts.append("elements: " + ", ".join(seg["notable_elements"]))
    return ". ".join(parts)
