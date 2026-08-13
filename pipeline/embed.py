"""Generate embeddings for dialogue and visual segments."""

from concurrent.futures import ThreadPoolExecutor

from google import genai

from agent import config

EMBED_MODEL = "gemini-embedding-001"  # text-embedding-004 was deprecated 2026-01-14
MAX_WORKERS = 8

# gemini-embedding-001's default output dimensionality (no output_dimensionality
# passed to embed_content). Every embedding already stored in ClickHouse's
# Array(Float32) embedding columns (schema/clickhouse.sql) was written at this
# size -- confirmed against live data via `SELECT length(embedding) FROM
# DailiesRoom.dialogue LIMIT 1`. If this ever changes (e.g. passing
# output_dimensionality explicitly, or a model swap), every stored row needs
# re-ingesting to match, or cosineDistance() calls in agent/tools/search.py
# and agent/tools/takes.py fail confusingly at the ClickHouse level instead of
# erroring clearly here.
EMBEDDING_DIM = 3072


class EmbeddingDimensionError(ValueError):
    """An embed_content() call returned a vector of unexpected dimensionality."""


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings.

    gemini-embedding-001 accepts exactly one text per request (unlike the
    old text-embedding-004, which took up to five) -- so "batch" here means
    fanning the per-text calls out across a thread pool rather than a single
    multi-text call.

    Validates each vector's dimensionality against EMBEDDING_DIM before
    returning, so a model/config change surfaces here -- at the one place
    every embedding call (ingest and query) passes through -- as a clear
    EmbeddingDimensionError instead of a cryptic ClickHouse failure later.
    """
    client = genai.Client(vertexai=True, project=config.PROJECT_ID, location=config.LOCATION)

    def embed_one(text: str) -> list[float]:
        vec = client.models.embed_content(model=EMBED_MODEL, contents=text).embeddings[0].values
        if len(vec) != EMBEDDING_DIM:
            raise EmbeddingDimensionError(
                f"embed_content returned a {len(vec)}-dim vector, expected {EMBEDDING_DIM}"
            )
        return vec

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        return list(pool.map(embed_one, texts))


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
