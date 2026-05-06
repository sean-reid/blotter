export interface ScannerEvent {
  feed_id: string;
  archive_ts: string;
  event_ts: string;
  raw_location: string;
  normalized: string;
  latitude: number;
  longitude: number;
  confidence: number;
  context: string;
  tags: string;
  window_id: string;
  summary: string;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

export interface TranscriptResult {
  feed_id: string;
  feed_name: string;
  archive_ts: string;
  duration_ms: number;
  audio_url: string;
  transcript: string;
  segments: string;
  tags: string;
  context: string;
}

export interface RelatedFeedEvent {
  feed_id: string;
  event_ts: string;
  normalized: string;
  window_id: string;
  summary: string;
}

export interface TimeRange {
  start: number;
  end: number;
}
