ATTACH TABLE _ UUID '204aef75-a7ca-4a3e-860d-8c660654c963'
(
    `clip_id` String,
    `segment_idx` UInt16,
    `scene` String,
    `take` UInt8,
    `start_s` Float32,
    `end_s` Float32,
    `description` String,
    `shot_type` String,
    `camera_movement` String,
    `characters_visible` Array(String),
    `notable_elements` Array(String),
    `embedding` Array(Float32)
)
ENGINE = MergeTree
ORDER BY (scene, clip_id, start_s)
SETTINGS index_granularity = 8192
