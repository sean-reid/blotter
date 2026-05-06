ALTER TABLE blotter.scanner_transcripts ADD COLUMN IF NOT EXISTS embedding Array(Float32) DEFAULT [];
