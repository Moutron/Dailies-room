CREATE DATABASE IF NOT EXISTS DailiesRoom;

-- LowCardinality(String) below marks columns bounded by production scope
-- (a handful to a few hundred distinct values even on a large shoot: scene
-- count, slate count, cast size, location count, camera card count) rather
-- than free text. dominant_mood is deliberately left as plain String: it's
-- a free-text mood phrase the model writes per clip, not drawn from a fixed
-- vocabulary -- every clip in the current sample has a distinct value.

-- One row per clip. Small table, joined for context.
CREATE TABLE IF NOT EXISTS DailiesRoom.clips (
    clip_id             String,
    source              String,
    scene               LowCardinality(String),
    slate               LowCardinality(String),
    take                UInt8,
    location            LowCardinality(String),
    day_night           LowCardinality(String),
    int_ext             LowCardinality(String),
    duration_s          Float32,
    summary             String,
    dominant_mood       String,
    characters_present  Array(String),
    characters_expected Array(String),
    technical_notes     Array(String),
    gcs_uri             String,
    -- Camera reel/card and the source (not clip-relative) timecode at the
    -- clip's first frame. Without these, every clip's dialogue/visual hits
    -- report the same clip-relative range starting at 00:00:00:00, which is
    -- useless to an editor trying to find the shot on the actual card.
    reel                LowCardinality(String),
    tc_start_s          Float32 DEFAULT 0,
    -- Version column for ReplacingMergeTree: re-ingesting the same clip_id
    -- inserts a new row with a newer ingested_at instead of requiring a
    -- TRUNCATE first; on merge (or `OPTIMIZE ... FINAL`), the row with the
    -- highest ingested_at for a given (scene, slate, take) wins. See
    -- pipeline/ingest.py.
    ingested_at         DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
-- clip_id, not just (scene, slate, take): this manifest reuses the same
-- take number for multiple distinct clips (e.g. 01_1a_take/01_1b_take/
-- 01_1c_take are all S01/1A/take 1 — different line reads, not re-slates
-- of the same setup), so (scene, slate, take) alone isn't a unique key.
-- Without clip_id here, ReplacingMergeTree silently treats those as the
-- same row and collapses them on merge — caught by re-running ingest
-- twice and finding clip count had dropped after the ReplacingMergeTree
-- migration.
ORDER BY (scene, slate, take, clip_id);

-- One row per line of dialogue. This is the table search hits most.
-- reel/tc_start_s are denormalized from clips (like scene/take already are)
-- so search_dialogue can compute source timecode without a join.
CREATE TABLE IF NOT EXISTS DailiesRoom.dialogue (
    clip_id     String,
    segment_idx UInt16,
    scene       LowCardinality(String),
    take        UInt8,
    start_s     Float32,
    end_s       Float32,
    speaker     LowCardinality(String),
    text        String,
    delivery    String,
    intensity   Float32,
    reel        LowCardinality(String),
    tc_start_s  Float32 DEFAULT 0,
    embedding   Array(Float32),
    ingested_at DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (scene, clip_id, start_s);

-- One row per visual beat.
--
-- shot_type is Enum8, mirroring pipeline/schema.py's SHOT_TYPES Literal
-- (the model's actual output vocabulary) -- keep the two lists in sync by
-- hand; TIGHT_SHOT_TYPES in that same file classifies which of these count
-- as "tight" for agent/tools/coverage.py's gap logic and is untouched here.
CREATE TABLE IF NOT EXISTS DailiesRoom.visuals (
    clip_id            String,
    segment_idx        UInt16,
    scene              LowCardinality(String),
    take               UInt8,
    start_s            Float32,
    end_s              Float32,
    description        String,
    shot_type          Enum8(
        'extreme_wide' = 1,
        'wide' = 2,
        'medium' = 3,
        'medium_close' = 4,
        'close' = 5,
        'extreme_close' = 6,
        'insert' = 7,
        'unknown' = 8
    ),
    camera_movement    LowCardinality(String),
    characters_visible Array(String),
    notable_elements   Array(String),
    reel               LowCardinality(String),
    tc_start_s         Float32 DEFAULT 0,
    embedding          Array(Float32),
    ingested_at        DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (scene, clip_id, start_s);
