"""The structured output every clip is reduced to."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Single source of truth for shot-type vocabulary, so agent/tools/coverage.py's
# tight-shot classification can't silently drift from what the model is
# actually allowed to emit.
SHOT_TYPES: tuple[str, ...] = (
    "extreme_wide",
    "wide",
    "medium",
    "medium_close",
    "close",
    "extreme_close",
    "insert",
    "unknown",
)

TIGHT_SHOT_TYPES: frozenset[str] = frozenset({"close", "extreme_close", "medium_close"})

# A spoken line shorter than this is almost certainly a bad timestamp, not
# real speech -- observed live: Gemini returned S01's dialogue end_s values
# as near-zero offsets from start_s (e.g. 0.001 -> 0.025), producing
# one-frame timecode ranges. pipeline/understand.py repairs segments this
# validator would otherwise reject by deriving end_s from context rather
# than silently accepting sub-frame durations.
MIN_DIALOGUE_DURATION_S = 0.15


class DialogueSegment(BaseModel):
    start_s: float = Field(description="Seconds from clip start")
    end_s: float
    speaker: str = Field(description="Character name, or 'UNKNOWN'")
    text: str
    delivery: str = Field(
        description="How the line is performed: e.g. 'clipped, angry', " "'quiet and hesitant'"
    )
    intensity: float = Field(description="Emotional intensity, 0.0 (flat) to 1.0 (extreme)")

    @model_validator(mode="after")
    def _reject_degenerate_duration(self) -> "DialogueSegment":
        duration = self.end_s - self.start_s
        if duration < MIN_DIALOGUE_DURATION_S:
            raise ValueError(
                f"dialogue segment duration {duration:.3f}s (start_s={self.start_s}, "
                f"end_s={self.end_s}) is below the minimum {MIN_DIALOGUE_DURATION_S}s -- "
                "reject rather than silently keep a sub-frame timestamp"
            )
        return self


class VisualSegment(BaseModel):
    start_s: float
    end_s: float
    description: str = Field(description="What is visible, plainly stated")
    shot_type: Literal[SHOT_TYPES]
    characters_visible: list[str]
    camera_movement: str = Field(description="static, pan, tilt, handheld, dolly")
    notable_elements: list[str] = Field(
        description="Props, wardrobe, set dressing a continuity supervisor " "would track"
    )


class ClipAnalysis(BaseModel):
    clip_id: str
    summary: str = Field(description="One sentence: what happens in this clip")
    dialogue: list[DialogueSegment]
    visuals: list[VisualSegment]
    characters_present: list[str]
    dominant_mood: str
    technical_notes: list[str] = Field(
        description="Problems an editor would flag: soft focus, boom in frame, "
        "flubbed line, clipped audio"
    )
