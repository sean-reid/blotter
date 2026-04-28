CREATE DATABASE IF NOT EXISTS blotter;

CREATE TABLE IF NOT EXISTS blotter.scanner_transcripts (
    feed_id       LowCardinality(String),
    feed_name     String,
    archive_ts    DateTime64(3),
    duration_ms   UInt32,
    audio_url     String,
    transcript    String,
    segments      String DEFAULT '',
    tags          String DEFAULT '',
    created_at    DateTime64(3) DEFAULT now64(3)
) ENGINE = MergeTree()
ORDER BY (feed_id, archive_ts);

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
    context       String DEFAULT '',
    tags          String DEFAULT '',
    created_at    DateTime64(3) DEFAULT now64(3)
) ENGINE = MergeTree()
ORDER BY (toDate(event_ts), h3_index, event_ts);

CREATE TABLE IF NOT EXISTS blotter.pipeline_metrics (
    ts       DateTime64(3) DEFAULT now64(3),
    metric   LowCardinality(String),
    value    Float64,
    tags     Map(String, String) DEFAULT map(),
    message  String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (metric, ts)
TTL toDateTime(ts) + INTERVAL 30 DAY;

-- Password set via ALTER USER after startup; placeholder for initial creation only
CREATE USER IF NOT EXISTS blotter_readonly IDENTIFIED BY 'changeme'
SETTINGS PROFILE 'readonly';
GRANT SELECT ON blotter.* TO blotter_readonly;
