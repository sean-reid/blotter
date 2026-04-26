export interface ScannerEvent {
  feed_id: string;
  archive_ts: string;
  event_ts: string;
  raw_location: string;
  normalized: string;
  latitude: number;
  longitude: number;
  confidence: number;
}

export interface TranscriptResult {
  feed_id: string;
  feed_name: string;
  archive_ts: string;
  duration_ms: number;
  audio_url: string;
  transcript: string;
}

export interface TimeRange {
  start: number;
  end: number;
}
