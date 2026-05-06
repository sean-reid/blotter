-- Move embeddings to dedicated table to isolate Array(Float32) merge pressure
-- from the main transcript table. Cap merge size on both tables.

CREATE TABLE IF NOT EXISTS blotter.transcript_embeddings (
    feed_id       LowCardinality(String),
    archive_ts    DateTime64(3),
    embedding     Array(Float32),
    created_at    DateTime64(3) DEFAULT now64(3)
) ENGINE = MergeTree()
ORDER BY (feed_id, archive_ts)
TTL toDateTime(archive_ts) + INTERVAL 7 DAY
SETTINGS max_bytes_to_merge_at_max_space_in_pool = 1073741824;

INSERT INTO blotter.transcript_embeddings (feed_id, archive_ts, embedding)
SELECT feed_id, archive_ts, embedding
FROM blotter.scanner_transcripts
WHERE length(embedding) > 0;

ALTER TABLE blotter.scanner_transcripts DROP COLUMN IF EXISTS embedding;

ALTER TABLE blotter.scanner_transcripts MODIFY SETTING max_bytes_to_merge_at_max_space_in_pool = 1073741824;
