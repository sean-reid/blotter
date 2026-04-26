from datetime import datetime, timezone

from blotter.models import ArchiveBlock, ExtractedLocation, GeocodedEvent, Transcript, TranscriptSegment


class TestArchiveBlock:
    def test_construction(self):
        block = ArchiveBlock(
            feed_id="12345",
            feed_name="SJPD",
            timestamp=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            duration_ms=1800000,
            url="https://example.com/archive.mp3",
        )
        assert block.feed_id == "12345"
        assert block.duration_ms == 1800000


class TestTranscript:
    def test_construction(self):
        t = Transcript(
            feed_id="12345",
            feed_name="SJPD",
            archive_ts=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            duration_ms=1800000,
            audio_url="https://example.com/archive.mp3",
            segments=[
                TranscriptSegment(start=0.0, end=5.0, text="Unit 5 responding"),
            ],
            full_text="Unit 5 responding",
        )
        assert len(t.segments) == 1
        assert t.full_text == "Unit 5 responding"


class TestExtractedLocation:
    def test_construction(self):
        loc = ExtractedLocation(
            raw_text="500 block of Main",
            normalized="550 Main Street",
            confidence=0.7,
            source="regex_block",
        )
        assert loc.confidence == 0.7


class TestGeocodedEvent:
    def test_construction(self):
        event = GeocodedEvent(
            feed_id="12345",
            archive_ts=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            event_ts=datetime(2025, 1, 15, 12, 5, 0, tzinfo=timezone.utc),
            raw_location="Main and 1st",
            normalized="Main Street and 1st Street, San Jose, CA",
            latitude=37.3382,
            longitude=-121.8863,
            confidence=0.75,
        )
        assert event.latitude == 37.3382
