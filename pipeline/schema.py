"""The structured output every clip is reduced to."""

from typing import Literal

from pydantic import BaseModel, Field


class DialogueSegment(BaseModel):
    start_s: float = Field(description="Seconds from clip start")
    end_s: float
    speaker: str = Field(description="Character name, or 'UNKNOWN'")
    text: str
    delivery: str = Field(
        description="How the line is performed: e.g. 'clipped, angry', " "'quiet and hesitant'"
    )
    intensity: float = Field(description="Emotional intensity, 0.0 (flat) to 1.0 (extreme)")


class VisualSegment(BaseModel):
    start_s: float
    end_s: float
    description: str = Field(description="What is visible, plainly stated")
    shot_type: Literal[
        "extreme_wide",
        "wide",
        "medium",
        "medium_close",
        "close",
        "extreme_close",
        "insert",
        "unknown",
    ]
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
