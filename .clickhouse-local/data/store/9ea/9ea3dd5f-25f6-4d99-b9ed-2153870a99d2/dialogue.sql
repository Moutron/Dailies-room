ATTACH TABLE _ UUID '7ec0acac-f9ad-46e7-a358-62a4bc9a98c8'
(
    `clip_id` String,
    `segment_idx` UInt16,
    `scene` String,
    `take` UInt8,
    `start_s` Float32,
    `end_s` Float32,
    `speaker` String,
    `text` String,
    `delivery` String,
    `intensity` Float32,
    `embedding` Array(Float32)
)
ENGINE = MergeTree
ORDER BY (scene, clip_id, start_s)
SETTINGS index_granularity = 8192
