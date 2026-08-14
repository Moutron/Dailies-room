"""Tests for pipeline/understand.py's dialogue-timing repair logic."""

import json
from unittest.mock import MagicMock, patch

import pytest

from pipeline.understand import (
    DegenerateDialogueTimingError,
    _derive_dialogue_durations,
    _has_degenerate_dialogue,
    analyse_clip,
)


class TestHasDegenerateDialogue:
    def test_flags_sub_frame_duration(self):
        assert _has_degenerate_dialogue([{"start_s": 0.0, "end_s": 0.04}])

    def test_accepts_real_duration(self):
        assert not _has_degenerate_dialogue([{"start_s": 0.0, "end_s": 2.0}])

    def test_empty_list_is_not_degenerate(self):
        assert not _has_degenerate_dialogue([])

    def test_one_bad_segment_among_good_ones_still_flags(self):
        segs = [{"start_s": 0.0, "end_s": 2.0}, {"start_s": 2.0, "end_s": 2.01}]
        assert _has_degenerate_dialogue(segs)


class TestDeriveDialogueDurations:
    def test_each_line_ends_where_next_starts(self):
        segs = [
            {"start_s": 0.0, "end_s": 0.01, "text": "a"},
            {"start_s": 1.0, "end_s": 1.02, "text": "b"},
        ]
        fixed = _derive_dialogue_durations(segs, clip_duration_s=3.0)

        assert fixed[0]["end_s"] == 1.0
        assert fixed[1]["end_s"] == 3.0

    def test_last_line_ends_at_clip_duration(self):
        segs = [{"start_s": 2.5, "end_s": 2.51, "text": "only line"}]
        fixed = _derive_dialogue_durations(segs, clip_duration_s=3.0)
        assert fixed[0]["end_s"] == 3.0

    def test_never_produces_a_degenerate_duration_even_if_duration_is_tiny(self):
        segs = [{"start_s": 2.9, "end_s": 2.91, "text": "last"}]
        fixed = _derive_dialogue_durations(segs, clip_duration_s=2.95)
        assert not _has_degenerate_dialogue(fixed)

    def test_does_not_mutate_input(self):
        segs = [{"start_s": 0.0, "end_s": 0.01, "text": "a"}]
        _derive_dialogue_durations(segs, clip_duration_s=3.0)
        assert segs[0]["end_s"] == 0.01


def _clip_analysis_payload(dialogue):
    return {
        "clip_id": "placeholder",
        "summary": "s",
        "dialogue": dialogue,
        "visuals": [],
        "characters_present": [],
        "dominant_mood": "neutral",
        "technical_notes": [],
    }


def _mock_gemini_response(payload):
    resp = MagicMock()
    resp.text = json.dumps(payload)
    return resp


class TestAnalyseClip:
    def test_derives_end_s_when_gemini_returns_degenerate_durations_and_duration_known(self):
        payload = _clip_analysis_payload(
            [
                {
                    "start_s": 0.0,
                    "end_s": 0.02,
                    "speaker": "MAN",
                    "text": "hi",
                    "delivery": "flat",
                    "intensity": 0.1,
                }
            ]
        )
        with patch("pipeline.understand.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.return_value = _mock_gemini_response(payload)

            analysis = analyse_clip(
                "01_1a_take", "gs://bucket/clips/01_1a_take.mp4", clip_duration_s=5.5
            )

            assert analysis.clip_id == "01_1a_take"
            assert analysis.dialogue[0].end_s == 5.5
            assert analysis.dialogue[0].start_s == 0.0

    def test_raises_when_degenerate_and_no_duration_available(self):
        payload = _clip_analysis_payload(
            [
                {
                    "start_s": 0.0,
                    "end_s": 0.02,
                    "speaker": "MAN",
                    "text": "hi",
                    "delivery": "flat",
                    "intensity": 0.1,
                }
            ]
        )
        with patch("pipeline.understand.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.return_value = _mock_gemini_response(payload)

            with pytest.raises(DegenerateDialogueTimingError):
                analyse_clip("01_1a_take", "gs://bucket/clips/01_1a_take.mp4")

    def test_leaves_real_durations_untouched(self):
        payload = _clip_analysis_payload(
            [
                {
                    "start_s": 0.0,
                    "end_s": 2.4,
                    "speaker": "MAN",
                    "text": "hi",
                    "delivery": "flat",
                    "intensity": 0.1,
                }
            ]
        )
        with patch("pipeline.understand.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.return_value = _mock_gemini_response(payload)

            analysis = analyse_clip("clip", "gs://bucket/clips/clip.mp4", clip_duration_s=5.0)

            assert analysis.dialogue[0].end_s == 2.4
