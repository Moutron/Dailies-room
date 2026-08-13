CREATE DATABASE IF NOT EXISTS DailiesRoom;

-- One row per clip. Small table, joined for context.
CREATE TABLE IF NOT EXISTS DailiesRoom.clips (
    clip_id             String,
    source              String,
    scene               String,
    slate               String,
    take                UInt8,
    location            String,
    day_night           String,
    int_ext             String,
    duration_s          Float32,
    summary             String,
    dominant_mood       String,
    characters_present  Array(String),
    characters_expected Array(String),
    technical_notes     Array(String),
    gcs_uri             String,
    processed_at        DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (scene, slate, take);

-- One row per line of dialogue. This is the table search hits most.
CREATE TABLE IF NOT EXISTS DailiesRoom.dialogue (
    clip_id     String,
    segment_idx UInt16,
    scene       String,
    take        UInt8,
    start_s     Float32,
    end_s       Float32,
    speaker     String,
    text        String,
    delivery    String,
    intensity   Float32,
    embedding   Array(Float32)
)
ENGINE = MergeTree
ORDER BY (scene, clip_id, start_s);

-- One row per visual beat.
CREATE TABLE IF NOT EXISTS DailiesRoom.visuals (
    clip_id            String,
    segment_idx        UInt16,
    scene              String,
    take               UInt8,
    start_s            Float32,
    end_s              Float32,
    description        String,
    shot_type          String,
    camera_movement    String,
    characters_visible Array(String),
    notable_elements   Array(String),
    embedding          Array(Float32)
)
ENGINE = MergeTree
ORDER BY (scene, clip_id, start_s);
