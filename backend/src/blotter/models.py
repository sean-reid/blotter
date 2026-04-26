from datetime import datetime

from pydantic import BaseModel


class ArchiveBlock(BaseModel):
    feed_id: str
    feed_name: str
    timestamp: datetime
    duration_ms: int
    url: str


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class Transcript(BaseModel):
    feed_id: str
    feed_name: str
    archive_ts: datetime
    duration_ms: int
    audio_url: str
    segments: list[TranscriptSegment]
    full_text: str


class ExtractedLocation(BaseModel):
    raw_text: str
    normalized: str
    confidence: float
    source: str  # "regex", "usaddress", "ner"


class GeocodedEvent(BaseModel):
    feed_id: str
    archive_ts: datetime
    event_ts: datetime
    raw_location: str
    normalized: str
    latitude: float
    longitude: float
    confidence: float
