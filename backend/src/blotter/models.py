from datetime import datetime

from pydantic import BaseModel


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
    tags: list[str] = []


class ExtractedLocation(BaseModel):
    raw_text: str
    normalized: str
    confidence: float
    source: str
    context: str = ""


class GeocodedEvent(BaseModel):
    feed_id: str
    archive_ts: datetime
    event_ts: datetime
    raw_location: str
    normalized: str
    latitude: float
    longitude: float
    confidence: float
    context: str = ""
    tags: list[str] = []


class ChunkTask(BaseModel):
    feed_id: str
    feed_name: str
    chunk_path: str
    audio_url: str
    chunk_ts: datetime
    chunk_index: int
    duration_ms: int
    skip_start: bool = False


class TranscriptTask(BaseModel):
    feed_id: str
    feed_name: str
    chunk_ts: datetime
    duration_ms: int
    audio_url: str
    segments: list[TranscriptSegment]
    full_text: str
    tags: list[str] = []
