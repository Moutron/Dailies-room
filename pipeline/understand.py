"""Gemini video analysis. One call per clip, cached to disk."""

import json
from pathlib import Path

from google import genai
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from agent import config
from pipeline.schema import MIN_DIALOGUE_DURATION_S, ClipAnalysis

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
- For each dialogue line's end_s, use the timestamp where the line actually
  finishes being spoken — listen for where the audio for that line stops, not
  where the next line begins or where you noticed the line started. end_s
  must be meaningfully after start_s (real spoken lines run at least half a
  second, most run several seconds); a near-zero duration is always wrong and
  will be rejected.
"""


class DegenerateDialogueTimingError(ValueError):
    """Gemini returned dialogue segments with unusable (near-zero) durations."""


def _has_degenerate_dialogue(raw_dialogue: list[dict]) -> bool:
    return any((seg["end_s"] - seg["start_s"]) < MIN_DIALOGUE_DURATION_S for seg in raw_dialogue)


def _derive_dialogue_durations(raw_dialogue: list[dict], clip_duration_s: float) -> list[dict]:
    """Fall back when Gemini's own end_s values are unusable.

    Each line is assumed to end where the next line starts; the last line
    ends at the clip's real (ffprobe-measured) duration. These timings are
    DERIVED, not observed — callers must not present them as Gemini's
    transcription of when a line stopped, only as a reasonable estimate
    computed from neighbouring lines.
    """
    fixed = []
    for i, seg in enumerate(raw_dialogue):
        next_start = (
            raw_dialogue[i + 1]["start_s"] if i + 1 < len(raw_dialogue) else clip_duration_s
        )
        seg = dict(seg)
        # +1e-3 headroom: MIN_DIALOGUE_DURATION_S exactly would round-trip
        # through float subtraction back below the validator's threshold.
        seg["end_s"] = max(next_start, seg["start_s"] + MIN_DIALOGUE_DURATION_S + 1e-3)
        fixed.append(seg)
    return fixed


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=4, max=60),
    retry=retry_if_not_exception_type(DegenerateDialogueTimingError),
)
def analyse_clip(clip_id: str, gcs_uri: str, clip_duration_s: float | None = None) -> ClipAnalysis:
    """Analyse one clip. Raises on repeated failure rather than returning junk.

    If Gemini returns dialogue with sub-frame durations and a real clip
    duration is available (ffprobe, not a guess), derive end_s from
    neighbouring lines instead of retrying the model call again — repeated
    attempts were observed to keep returning the same degenerate values, so
    retrying past the point where we have a real duration to derive from
    just burns quota. Without a duration to derive from, this raises
    DegenerateDialogueTimingError instead of silently accepting bad data.
    """
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

    raw = json.loads(response.text)
    if _has_degenerate_dialogue(raw.get("dialogue", [])):
        if clip_duration_s is None:
            raise DegenerateDialogueTimingError(
                f"{clip_id}: Gemini returned sub-{MIN_DIALOGUE_DURATION_S}s dialogue "
                "durations and no real clip_duration_s was supplied to derive from"
            )
        raw["dialogue"] = _derive_dialogue_durations(raw["dialogue"], clip_duration_s)

    analysis = ClipAnalysis.model_validate(raw)
    analysis.clip_id = clip_id
    return analysis


def process(
    clip_id: str, gcs_uri: str, force: bool = False, clip_duration_s: float | None = None
) -> ClipAnalysis:
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
    analysis = analyse_clip(clip_id, gcs_uri, clip_duration_s=clip_duration_s)
    cache.write_text(analysis.model_dump_json(indent=2))
    return analysis
