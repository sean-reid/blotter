CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS scanner_transcripts (
    id          BIGSERIAL PRIMARY KEY,
    feed_id     TEXT NOT NULL,
    feed_name   TEXT NOT NULL,
    archive_ts  TIMESTAMPTZ(3) NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    audio_url   TEXT NOT NULL DEFAULT '',
    transcript  TEXT NOT NULL DEFAULT '',
    segments    TEXT NOT NULL DEFAULT '[]',
    tags        TEXT NOT NULL DEFAULT '',
    window_id   TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ(3) NOT NULL DEFAULT now(),
    UNIQUE (feed_id, archive_ts)
);

CREATE INDEX IF NOT EXISTS idx_transcripts_feed_archive ON scanner_transcripts (feed_id, archive_ts);
CREATE INDEX IF NOT EXISTS idx_transcripts_archive_ts ON scanner_transcripts (archive_ts);
CREATE INDEX IF NOT EXISTS idx_transcripts_window_id ON scanner_transcripts (window_id) WHERE window_id != '';
CREATE INDEX IF NOT EXISTS idx_transcripts_trgm ON scanner_transcripts USING gin (transcript gin_trgm_ops);

CREATE TABLE IF NOT EXISTS scanner_events (
    id          BIGSERIAL PRIMARY KEY,
    feed_id     TEXT NOT NULL,
    archive_ts  TIMESTAMPTZ(3) NOT NULL,
    event_ts    TIMESTAMPTZ(3) NOT NULL,
    raw_location TEXT NOT NULL,
    normalized  TEXT NOT NULL,
    latitude    DOUBLE PRECISION NOT NULL,
    longitude   DOUBLE PRECISION NOT NULL,
    confidence  REAL NOT NULL,
    context     TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '',
    window_id   TEXT NOT NULL DEFAULT '',
    summary     TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ(3) NOT NULL DEFAULT now(),
    UNIQUE (feed_id, archive_ts, normalized)
);

CREATE INDEX IF NOT EXISTS idx_events_event_ts ON scanner_events (event_ts);
CREATE INDEX IF NOT EXISTS idx_events_feed_archive ON scanner_events (feed_id, archive_ts);
CREATE INDEX IF NOT EXISTS idx_events_spatial ON scanner_events (latitude, longitude);

CREATE TABLE IF NOT EXISTS transcript_embeddings (
    id          BIGSERIAL PRIMARY KEY,
    feed_id     TEXT NOT NULL,
    archive_ts  TIMESTAMPTZ(3) NOT NULL,
    embedding   REAL[] NOT NULL,
    created_at  TIMESTAMPTZ(3) NOT NULL DEFAULT now(),
    UNIQUE (feed_id, archive_ts)
);
