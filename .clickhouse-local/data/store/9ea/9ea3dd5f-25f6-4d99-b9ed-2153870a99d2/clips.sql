ATTACH TABLE _ UUID '6d8bc21c-b507-4bf9-8f1e-03bab8f5534b'
(
    `clip_id` String,
    `source` String,
    `scene` String,
    `slate` String,
    `take` UInt8,
    `location` String,
    `day_night` String,
    `int_ext` String,
    `duration_s` Float32,
    `summary` String,
    `dominant_mood` String,
    `characters_present` Array(String),
    `characters_expected` Array(String),
    `technical_notes` Array(String),
    `gcs_uri` String,
    `processed_at` DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (scene, slate, take)
SETTINGS index_granularity = 8192
