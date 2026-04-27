import signal
from datetime import datetime, timezone
from threading import Event

from blotter.config import (
    ClickHouseConfig, GCSConfig, GoogleGeocodingConfig, GoogleNLPConfig,
    RedisConfig, RegionConfig, StreamConfig, TranscriptionConfig,
)
from blotter.db import get_client, has_recent_event, insert_events, insert_transcript
from blotter.gcs import get_storage
from blotter.log import get_logger
from blotter.models import GeocodedEvent, Transcript, TranscriptTask
from blotter.queue import (
    dequeue_chunk, dequeue_transcript, enqueue_transcript, get_redis,
    queue_depth, CAPTURE_QUEUE, TRANSCRIPT_QUEUE,
)
from blotter.stages.capture import CaptureManager
from blotter.stages.extract import extract_clauses
from blotter.stages.extract_codes import extract_codes
from blotter.stages.extract_nlp import extract_entities
from blotter.stages.geocode import Geocoder
from blotter.stages.stream_transcribe import StreamTranscriber

log = get_logger(__name__)


def run_capture(
    stream_config: StreamConfig,
    gcs_config: GCSConfig,
    redis_config: RedisConfig,
) -> None:
    manager = CaptureManager(stream_config, gcs_config, redis_config)
    manager.start()


def run_transcriber(
    transcription_config: TranscriptionConfig,
    stream_config: StreamConfig,
    gcs_config: GCSConfig,
    redis_config: RedisConfig,
    ch_config: ClickHouseConfig,
) -> None:
    transcriber = StreamTranscriber(transcription_config, stream_config, gcs_config)
    storage = get_storage(gcs_config)
    r = get_redis(redis_config)
    ch = get_client(ch_config)
    stop = Event()

    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    log.info("transcription worker started")

    while not stop.is_set():
        task = dequeue_chunk(r, timeout=5)
        if task is None:
            continue

        try:
            segments, full_text, actual_duration_ms = transcriber.process_chunk(task)

            if not full_text:
                try:
                    storage.delete(task.chunk_path)
                except Exception:
                    log.debug("failed to delete empty chunk", chunk_path=task.chunk_path, exc_info=True)
                continue

            tags = extract_codes(full_text)
            duration_ms = actual_duration_ms or task.duration_ms

            transcript = Transcript(
                feed_id=task.feed_id,
                feed_name=task.feed_name,
                archive_ts=task.chunk_ts,
                duration_ms=duration_ms,
                audio_url=task.audio_url,
                segments=segments,
                full_text=full_text,
                tags=tags,
            )
            insert_transcript(ch, transcript)

            tt = TranscriptTask(
                feed_id=task.feed_id,
                feed_name=task.feed_name,
                chunk_ts=task.chunk_ts,
                duration_ms=duration_ms,
                audio_url=task.audio_url,
                segments=segments,
                full_text=full_text,
                tags=tags,
            )
            enqueue_transcript(r, tt)

            depth = queue_depth(r, CAPTURE_QUEUE)
            if depth > 50:
                log.warning("transcription backlog", depth=depth)

        except Exception:
            log.error("transcription failed", feed_id=task.feed_id, exc_info=True)

    log.info("transcription worker stopped")


def run_processor(
    redis_config: RedisConfig,
    ch_config: ClickHouseConfig,
    nlp_config: GoogleNLPConfig,
    geocoding_config: GoogleGeocodingConfig,
    region_config: RegionConfig,
) -> None:
    r = get_redis(redis_config)
    ch = get_client(ch_config)
    geocoder = Geocoder(geocoding_config, region_config)
    stop = Event()

    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    log.info("processing worker started")

    while not stop.is_set():
        task = dequeue_transcript(r, timeout=5)
        if task is None:
            continue

        try:
            entities = extract_entities(task.full_text, nlp_config)
            if not entities:
                entities = extract_clauses(task.full_text)

            events = []
            batch_coords: list[tuple[float, float]] = []
            for e in entities:
                result = geocoder.geocode(e)
                if result is None:
                    continue
                lat, lon, name = result
                if has_recent_event(ch, name, lat, lon, minutes=10):
                    log.debug("skipping duplicate event", normalized=name)
                    continue
                too_close = any(
                    abs(lat - blat) < 0.002 and abs(lon - blon) < 0.002
                    for blat, blon in batch_coords
                )
                if too_close:
                    log.debug("skipping batch duplicate", normalized=name)
                    continue
                batch_coords.append((lat, lon))
                events.append(GeocodedEvent(
                    feed_id=task.feed_id,
                    archive_ts=task.chunk_ts,
                    event_ts=datetime.now(timezone.utc),
                    raw_location=e.raw_text,
                    normalized=name,
                    latitude=lat,
                    longitude=lon,
                    confidence=0.8,
                    context=e.context,
                    tags=task.tags,
                ))

            insert_events(ch, events)
            log.info(
                "chunk processed",
                feed_id=task.feed_id,
                entities=len(entities),
                events=len(events),
            )

        except Exception:
            log.error("processing failed", feed_id=task.feed_id, exc_info=True)

    log.info("processing worker stopped")
