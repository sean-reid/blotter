from datetime import datetime, timezone
from pathlib import Path

from blotter.config import Settings
from blotter.db import get_client, insert_events, insert_transcript, transcript_exists
from blotter.log import get_logger
from blotter.models import ArchiveBlock, GeocodedEvent, Transcript
from blotter.stages.download import AudioDownloader
from blotter.stages.extract import extract_locations
from blotter.stages.fetch import BroadcastifyClient
from blotter.stages.geocode import Geocoder
from blotter.stages.transcribe import Transcriber

log = get_logger(__name__)


def run_pipeline(settings: Settings, feed_id: str, start: datetime | None = None, end: datetime | None = None) -> None:
    client = get_client(settings.clickhouse)
    bc = BroadcastifyClient(settings.broadcastify)
    downloader = AudioDownloader(settings.broadcastify, settings.data_dir)
    transcriber = Transcriber(settings.transcription)
    geocoder = Geocoder(settings.nominatim)

    try:
        blocks = bc.get_archives(feed_id, start=start, end=end)
        log.info("pipeline started", feed_id=feed_id, blocks=len(blocks))

        for block in blocks:
            archive_ts_str = block.timestamp.isoformat()
            if transcript_exists(client, feed_id, archive_ts_str):
                log.info("skipping existing", feed_id=feed_id, ts=archive_ts_str)
                continue

            wav_path = downloader.download_and_convert(block)
            segments, full_text = transcriber.transcribe(wav_path)

            transcript = Transcript(
                feed_id=block.feed_id,
                feed_name=block.feed_name,
                archive_ts=block.timestamp,
                duration_ms=block.duration_ms,
                audio_url=block.url,
                segments=segments,
                full_text=full_text,
            )
            insert_transcript(client, transcript)

            locations = extract_locations(full_text)
            events: list[GeocodedEvent] = []
            for loc in locations:
                coords = geocoder.geocode(loc)
                if coords is None:
                    continue
                events.append(GeocodedEvent(
                    feed_id=feed_id,
                    archive_ts=block.timestamp,
                    event_ts=block.timestamp,
                    raw_location=loc.raw_text,
                    normalized=loc.normalized,
                    latitude=coords[0],
                    longitude=coords[1],
                    confidence=loc.confidence,
                ))

            insert_events(client, events)
            log.info(
                "block complete",
                feed_id=feed_id,
                ts=archive_ts_str,
                locations=len(events),
            )

        log.info("pipeline complete", feed_id=feed_id)
    finally:
        bc.close()
        downloader.close()
