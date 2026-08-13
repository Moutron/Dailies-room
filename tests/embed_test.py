"""Tests for pipeline/embed.py's pure text-building helpers."""

from unittest.mock import MagicMock, patch

import pytest

from pipeline.embed import (
    EMBEDDING_DIM,
    EmbeddingDimensionError,
    dialogue_text,
    embed_batch,
    visual_text,
)


class TestDialogueText:
    def test_includes_speaker_text_and_delivery(self):
        seg = {"speaker": "CELIA", "text": "Where were you?", "delivery": "quiet, hesitant"}
        assert dialogue_text(seg) == "CELIA: Where were you? (delivered: quiet, hesitant)"


class TestVisualText:
    def test_minimal_segment(self):
        seg = {"description": "A wide shot of a bridge", "shot_type": "wide"}
        assert visual_text(seg) == "A wide shot of a bridge. shot type: wide"

    def test_includes_characters_and_notable_elements_when_present(self):
        seg = {
            "description": "A close-up",
            "shot_type": "close",
            "characters_visible": ["CELIA", "THOM"],
            "notable_elements": ["rifle", "green screen"],
        }
        assert visual_text(seg) == (
            "A close-up. shot type: close. featuring CELIA, THOM. elements: rifle, green screen"
        )

    def test_omits_empty_lists(self):
        seg = {
            "description": "A close-up",
            "shot_type": "close",
            "characters_visible": [],
            "notable_elements": [],
        }
        assert visual_text(seg) == "A close-up. shot type: close"


class TestEmbedBatch:
    def test_loops_once_per_text_and_returns_vectors(self):
        with patch("pipeline.embed.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            def embed_content(model, contents):
                resp = MagicMock()
                resp.embeddings = [MagicMock(values=[len(contents) * 1.0] * EMBEDDING_DIM)]
                return resp

            mock_client.models.embed_content.side_effect = embed_content

            result = embed_batch(["a", "bb"])

            assert result == [[1.0] * EMBEDDING_DIM, [2.0] * EMBEDDING_DIM]
            assert mock_client.models.embed_content.call_count == 2

    def test_raises_on_unexpected_dimension(self):
        with patch("pipeline.embed.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            resp = MagicMock()
            resp.embeddings = [MagicMock(values=[0.1, 0.2])]
            mock_client.models.embed_content.return_value = resp

            with pytest.raises(EmbeddingDimensionError):
                embed_batch(["a"])
