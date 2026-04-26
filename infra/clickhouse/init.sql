CREATE DATABASE IF NOT EXISTS blotter;

CREATE TABLE IF NOT EXISTS blotter.scanner_transcripts (
    feed_id       LowCardinality(String),
    feed_name     String,
    archive_ts    DateTime64(3),
    duration_ms   UInt32,
    audio_url     String,
    transcript    String,
    created_at    DateTime64(3) DEFAULT now64(3),
    INDEX idx_transcript transcript TYPE full_text(0) GRANULARITY 1
) ENGINE = MergeTree()
ORDER BY (feed_id, archive_ts)
SETTINGS allow_experimental_full_text_index = 1;

CREATE TABLE IF NOT EXISTS blotter.scanner_events (
    feed_id       LowCardinality(String),
    archive_ts    DateTime64(3),
    event_ts      DateTime64(3),
    raw_location  String,
    normalized    String,
    latitude      Float64,
    longitude     Float64,
    h3_index      UInt64 MATERIALIZED geoToH3(longitude, latitude, 9),
    confidence    Float32,
    created_at    DateTime64(3) DEFAULT now64(3)
) ENGINE = MergeTree()
ORDER BY (toDate(event_ts), h3_index, event_ts);

CREATE USER IF NOT EXISTS blotter_readonly IDENTIFIED BY 'readonly'
SETTINGS PROFILE 'readonly';
GRANT SELECT ON blotter.* TO blotter_readonly;
