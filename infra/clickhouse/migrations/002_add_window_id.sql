ALTER TABLE blotter.scanner_transcripts ADD COLUMN IF NOT EXISTS window_id String DEFAULT '';
ALTER TABLE blotter.scanner_events ADD COLUMN IF NOT EXISTS window_id String DEFAULT '';
