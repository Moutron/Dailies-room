"""Smoke test for pipeline/schema.py's structured output model."""

import pytest
from pydantic import ValidationError

from pipeline.schema import ClipAnalysis


def test_clip_analysis_round_trips_a_full_payload():
    payload = {
        "clip_id": "03_2a_take",
        "summary": "A wide shot of the bridge.",
        "dialogue": [
            {
                "start_s": 0.0,
                "end_s": 2.0,
                "speaker": "CELIA",
                "text": "Where were you?",
                "delivery": "quiet, hesitant",
                "intensity": 0.4,
            }
        ],
        "visuals": [
            {
                "start_s": 0.0,
                "end_s": 9.0,
                "description": "A wide shot of a film set.",
                "shot_type": "wide",
                "characters_visible": ["CELIA"],
                "camera_movement": "static",
                "notable_elements": ["green screen"],
            }
        ],
        "characters_present": ["CELIA"],
        "dominant_mood": "tense",
        "technical_notes": ["boom pole visible"],
    }

    analysis = ClipAnalysis.model_validate(payload)

    assert analysis.clip_id == "03_2a_take"
    assert analysis.dialogue[0].speaker == "CELIA"
    assert analysis.visuals[0].shot_type == "wide"
    assert analysis.model_dump()["dominant_mood"] == "tense"


def test_clip_analysis_rejects_invalid_shot_type():
    payload = {
        "clip_id": "c1",
        "summary": "s",
        "dialogue": [],
        "visuals": [
            {
                "start_s": 0.0,
                "end_s": 1.0,
                "description": "d",
                "shot_type": "not-a-real-shot-type",
                "characters_visible": [],
                "camera_movement": "static",
                "notable_elements": [],
            }
        ],
        "characters_present": [],
        "dominant_mood": "neutral",
        "technical_notes": [],
    }

    with pytest.raises(ValidationError):
        ClipAnalysis.model_validate(payload)
