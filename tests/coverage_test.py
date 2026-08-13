"""Tests for agent/tools/coverage.py."""

from unittest.mock import MagicMock, patch

import pytest

from agent.tools.coverage import get_coverage

COLUMNS = [
    "clip_id",
    "scene",
    "slate",
    "take",
    "location",
    "day_night",
    "summary",
    "characters_present",
    "characters_expected",
    "technical_notes",
    "reel",
    "tc_start_s",
    "shot_type",
    "camera_movement",
    "start_s",
    "end_s",
]

GAP_COLUMNS = ["expected", "present", "any_shot_chars", "tight_shot_chars"]


def _row(
    clip_id,
    slate,
    take,
    shot_type,
    characters_visible,
    characters_present=None,
    characters_expected=None,
    reel="A001",
    tc_start_s=0.0,
):
    return [
        clip_id,
        "S03",
        slate,
        take,
        "Bridge",
        "day",
        "summary",
        characters_present or characters_visible,
        characters_expected or ["CELIA", "THOM", "MARCO"],
        [],
        reel,
        tc_start_s,
        shot_type,
        "static",
        0.0,
        5.0,
    ]


def _gap_result(expected, present, any_shot_chars, tight_shot_chars):
    """The second query's mocked result: `_scene_gap_sets`'s SQL aggregate."""
    result = MagicMock()
    result.column_names = GAP_COLUMNS
    result.result_rows = [[expected, present, any_shot_chars, tight_shot_chars]]
    return result


@pytest.fixture
def mock_client():
    with patch("agent.tools.coverage.client") as mock_client:
        yield mock_client


@pytest.fixture
def mock_aliases():
    # Default map: every synthetic test name resolves only to itself, so
    # existing tests keep their pre-alias-resolution behavior. Individual
    # tests override this to exercise alias resolution and the unmatched path.
    aliases = {name: frozenset({name}) for name in ("CELIA", "THOM", "MARCO")}
    with patch("agent.tools.coverage._character_aliases", return_value=aliases):
        yield aliases


class TestGetCoverage:
    def test_no_scene_lists_every_scene_without_gap_fields(self, mock_client):
        result = MagicMock()
        result.column_names = COLUMNS
        result.result_rows = [_row("c1", "2A", 1, "wide", ["CELIA"])]
        mock_client.return_value.query.return_value = result

        rows = get_coverage()

        assert len(rows) == 1
        assert "never_appeared" not in rows[0]
        assert rows[0]["timecode_in"] == "00:00:00:00"
        assert "characters_visible" not in rows[0]

    def test_timecode_offset_by_source_tc_start(self, mock_client):
        result = MagicMock()
        result.column_names = COLUMNS
        result.result_rows = [
            _row("c1", "2A", 1, "wide", ["CELIA"], reel="A008", tc_start_s=3600.0)
        ]
        mock_client.return_value.query.return_value = result

        rows = get_coverage()

        assert rows[0]["reel"] == "A008"
        assert rows[0]["timecode_in"] == "01:00:00:00"
        assert rows[0]["timecode_out"] == "01:00:05:00"
        assert "tc_start_s" not in rows[0]

    def test_scene_computes_never_appeared(self, mock_client, mock_aliases):
        result = MagicMock()
        result.column_names = COLUMNS
        result.result_rows = [
            _row(
                "c1",
                "2A",
                1,
                "wide",
                ["CELIA"],
                characters_present=["CELIA"],
                characters_expected=["CELIA", "THOM"],
            ),
        ]
        mock_client.return_value.query.side_effect = [
            result,
            _gap_result(["CELIA", "THOM"], ["CELIA"], ["CELIA"], []),
        ]

        rows = get_coverage(scene="S03")

        assert rows[0]["never_appeared"] == ["THOM"]
        assert rows[0]["unmatched_expected"] == []

    def test_scene_computes_no_tight_shot(self, mock_client, mock_aliases):
        # CELIA appears, but only ever in a wide shot -> never in a tight shot.
        result = MagicMock()
        result.column_names = COLUMNS
        result.result_rows = [
            _row(
                "c1",
                "2A",
                1,
                "wide",
                ["CELIA"],
                characters_present=["CELIA"],
                characters_expected=["CELIA"],
            ),
        ]
        mock_client.return_value.query.side_effect = [
            result,
            _gap_result(["CELIA"], ["CELIA"], ["CELIA"], []),
        ]

        rows = get_coverage(scene="S03")

        assert rows[0]["no_tight_shot"] == ["CELIA"]
        assert rows[0]["wide_coverage"] == ["CELIA"]

    def test_scene_tight_shot_excludes_character_from_gaps(self, mock_client, mock_aliases):
        result = MagicMock()
        result.column_names = COLUMNS
        result.result_rows = [
            _row(
                "c1",
                "2A",
                1,
                "close",
                ["CELIA"],
                characters_present=["CELIA"],
                characters_expected=["CELIA"],
            ),
        ]
        mock_client.return_value.query.side_effect = [
            result,
            _gap_result(["CELIA"], ["CELIA"], ["CELIA"], ["CELIA"]),
        ]

        rows = get_coverage(scene="S03")

        assert rows[0]["no_tight_shot"] == []
        assert rows[0]["wide_coverage"] == []

    def test_scene_resolves_expected_character_through_alias(self, mock_client, mock_aliases):
        # "Bruno" was expected; Gemini only ever detected him as
        # "ACTOR_SITTING_WITH_RIFLE" in this clip. Without alias resolution
        # this reports him as never_appeared even though he's in the footage.
        mock_aliases["Bruno"] = frozenset({"Bruno", "ACTOR_SITTING_WITH_RIFLE", "UNKNOWN_MAN"})
        result = MagicMock()
        result.column_names = COLUMNS
        result.result_rows = [
            _row(
                "c1",
                "2A",
                1,
                "wide",
                ["ACTOR_SITTING_WITH_RIFLE"],
                characters_present=["ACTOR_SITTING_WITH_RIFLE"],
                characters_expected=["Bruno"],
            ),
        ]
        mock_client.return_value.query.side_effect = [
            result,
            _gap_result(["Bruno"], ["ACTOR_SITTING_WITH_RIFLE"], ["ACTOR_SITTING_WITH_RIFLE"], []),
        ]

        rows = get_coverage(scene="S03")

        assert rows[0]["never_appeared"] == []
        assert rows[0]["unmatched_expected"] == []

    def test_scene_expected_character_with_no_alias_entry_is_unmatched_not_absent(
        self, mock_client, mock_aliases
    ):
        # No alias entry exists for this name, so we can't confirm they're
        # actually absent — Gemini may just have named them something we
        # haven't curated. Must not land in never_appeared.
        result = MagicMock()
        result.column_names = COLUMNS
        result.result_rows = [
            _row(
                "c1",
                "2A",
                1,
                "wide",
                ["CELIA"],
                characters_present=["CELIA"],
                characters_expected=["Unidentified (newspaper reader)"],
            ),
        ]
        mock_client.return_value.query.side_effect = [
            result,
            _gap_result(["Unidentified (newspaper reader)"], ["CELIA"], ["CELIA"], []),
        ]

        rows = get_coverage(scene="S03")

        assert rows[0]["never_appeared"] == []
        assert rows[0]["unmatched_expected"] == ["Unidentified (newspaper reader)"]

    def test_unmatched_scene_reports_an_error_not_an_empty_result(self, mock_client):
        """An unknown scene must never look like a scene with no coverage.

        Returning [] here reads to the model as a confirmed negative, so it
        asserts "there's no coverage" when the truth is that the identifier
        never matched — the one false assertion the honesty prompt can't
        catch, since the tool is what told it so.
        """
        listing = MagicMock()
        listing.column_names = COLUMNS
        listing.result_rows = []
        scenes = MagicMock()
        scenes.result_rows = [["S01"], ["S03"]]
        mock_client.return_value.query.side_effect = [listing, scenes]

        rows = get_coverage(scene="the bridge scene")

        assert len(rows) == 1
        assert rows[0]["error_type"] == "unknown_scene"
        assert "the bridge scene" in rows[0]["error"]
        assert rows[0]["known_scenes"] == ["S01", "S03"]

    def test_unmatched_scene_skips_gap_computation(self, mock_client):
        """The gap aggregate must not run for a scene that doesn't exist."""
        listing = MagicMock()
        listing.column_names = COLUMNS
        listing.result_rows = []
        scenes = MagicMock()
        scenes.result_rows = [["S01"]]
        mock_client.return_value.query.side_effect = [listing, scenes]

        with patch("agent.tools.coverage._scene_gap_sets") as gap_sets:
            get_coverage(scene="S99")

        gap_sets.assert_not_called()

    def test_clickhouse_failure_returns_error_row(self, mock_client):
        mock_client.return_value.query.side_effect = RuntimeError("down")

        rows = get_coverage(scene="S03")

        assert rows == [
            {
                "error": "The footage index is unreachable (RuntimeError).",
                "error_type": "unreachable",
            }
        ]


class TestCharacterAliases:
    def test_loads_bruno_aliases_from_manifest(self):
        # Not mocked: exercises the real data/manifest.json, which is the
        # asset the B1 fix depends on staying in sync with data/processed/.
        from agent.tools.coverage import _character_aliases

        _character_aliases.cache_clear()
        aliases = _character_aliases()

        assert "Bruno" in aliases
        assert {"Bruno", "ACTOR_SITTING_WITH_RIFLE", "UNKNOWN_MAN", "Man in Tactical Gear"} <= (
            aliases["Bruno"]
        )


class TestTightShotTypes:
    def test_every_shot_type_literal_value_is_classified(self):
        # Fails if pipeline/schema.py's SHOT_TYPES Literal gains a value that
        # nobody has decided is tight or not — the exact silent-drift failure
        # mode that made TIGHT_SHOT_TYPES wrong in the first place (it used
        # to share exactly one value, "close", with the real enum).
        from pipeline.schema import SHOT_TYPES, TIGHT_SHOT_TYPES

        expected_tightness = {
            "extreme_wide": False,
            "wide": False,
            "medium": False,
            "medium_close": True,
            "close": True,
            "extreme_close": True,
            "insert": False,
            "unknown": False,
        }

        assert set(expected_tightness) == set(SHOT_TYPES)
        for shot_type, is_tight in expected_tightness.items():
            assert (shot_type in TIGHT_SHOT_TYPES) == is_tight, shot_type
