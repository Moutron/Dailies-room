"""Gemini video analysis. One call per clip, cached to disk."""

from pathlib import Path

from google import genai
from tenacity import retry, stop_after_attempt, wait_exponential

from agent import config
from pipeline.schema import ClipAnalysis

PROCESSED_DIR = Path("data/processed")

ANALYSIS_PROMPT = """
You are a script supervisor and assistant editor reviewing a piece of raw
footage from a film shoot.

Analyse this clip and return structured data describing it.

Requirements:
- Timestamps are seconds from the start of THIS clip, not absolute timecode.
- Transcribe dialogue exactly as spoken, including stumbles and false starts.
  Do not clean it up — a flubbed line is information an editor needs.
- For each line, describe HOW it is delivered, not just what is said.
  Performance is the thing being judged in dailies.
- Identify characters by name where the dialogue makes it clear; otherwise use
  a consistent descriptor such as "MAN_IN_GREY".
- For notable_elements, list what a continuity supervisor would track:
  wardrobe, hand props, set dressing, weather, practical lighting.
- For technical_notes, flag anything an editor would care about: soft focus,
  boom or crew in frame, audio problems, flubbed lines, continuity errors.
- If you cannot determine something, say so. Do not guess a character name or
  invent a timestamp. Wrong metadata is worse than missing metadata, because
  someone will act on it.
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=60))
def analyse_clip(clip_id: str, gcs_uri: str) -> ClipAnalysis:
    """Analyse one clip. Raises on repeated failure rather than returning junk."""
    client = genai.Client(vertexai=True, project=config.PROJECT_ID, location=config.LOCATION)

    response = client.models.generate_content(
        model=config.VIDEO_MODEL,
        contents=[
            {"file_data": {"file_uri": gcs_uri, "mime_type": "video/mp4"}},
            ANALYSIS_PROMPT,
        ],
        config={
            "response_mime_type": "application/json",
            "response_schema": ClipAnalysis,
            "temperature": 0.1,
        },
    )

    analysis = ClipAnalysis.model_validate_json(response.text)
    analysis.clip_id = clip_id
    return analysis


def process(clip_id: str, gcs_uri: str, force: bool = False) -> ClipAnalysis:
    """Analyse a clip, or return the cached result if we already have it.

    No caller in this repo currently loops this over multiple clips -- each
    clip has been processed individually so far. If a batch script is added
    later, isolate failures per clip there (this function still raises after
    analyse_clip()'s 3 retries are exhausted) so one bad clip doesn't abort
    the whole run.
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    cache = PROCESSED_DIR / f"{clip_id}.json"

    if cache.exists() and not force:
        print(f"  cached: {clip_id}")
        return ClipAnalysis.model_validate_json(cache.read_text())

    print(f"  analysing: {clip_id}")
    analysis = analyse_clip(clip_id, gcs_uri)
    cache.write_text(analysis.model_dump_json(indent=2))
    return analysis
