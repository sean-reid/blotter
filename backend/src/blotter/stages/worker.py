import signal
import time
from threading import Event

from blotter.config import (
    ClickHouseConfig, GCSConfig, GoogleGeocodingConfig, GoogleNLPConfig,
    OpenMhzConfig, RedisConfig, RegionConfig, StreamConfig, TranscriptionConfig,
)
from blotter.db import fetch_surrounding_context, get_client, has_recent_event, insert_events, insert_transcript, transcript_exists
from blotter.gcs import get_storage
from blotter.log import get_logger
from blotter.models import GeocodedEvent, Transcript, TranscriptTask
from blotter.queue import (
    dequeue_chunk, dequeue_transcript, enqueue_transcript, get_redis,
    queue_depth, CAPTURE_QUEUE, TRANSCRIPT_QUEUE,
)
from blotter.stages.capture import CaptureManager
from blotter.stages.capture_openmhz import OpenMhzCaptureManager
from blotter.stages.extract import extract_clauses
from blotter.stages.extract_codes import extract_codes
from blotter.stages.extract_nlp import extract_entities
from blotter.stages.geocode import Geocoder
from blotter.stages.stream_transcribe import StreamTranscriber

log = get_logger(__name__)


def _connect_clickhouse(ch_config: ClickHouseConfig, max_retries: int = 30, delay: int = 5):
    for attempt in range(1, max_retries + 1):
        try:
            ch = get_client(ch_config)
            ch.command("SELECT 1")
            return ch
        except Exception:
            if attempt == max_retries:
                raise
            log.warning("clickhouse not ready, retrying", attempt=attempt, delay=delay)
            time.sleep(delay)


def run_capture(
    stream_config: StreamConfig,
    gcs_config: GCSConfig,
    redis_config: RedisConfig,
) -> None:
    manager = CaptureManager(stream_config, gcs_config, redis_config)
    manager.start()


def run_capture_openmhz(
    openmhz_config: OpenMhzConfig,
    gcs_config: GCSConfig,
    redis_config: RedisConfig,
) -> None:
    manager = OpenMhzCaptureManager(openmhz_config, gcs_config, redis_config)
    manager.start()


def run_transcriber(
    transcription_config: TranscriptionConfig,
    stream_config: StreamConfig,
    gcs_config: GCSConfig,
    redis_config: RedisConfig,
    ch_config: ClickHouseConfig,
    num_threads: int = 1,
) -> None:
    from threading import Thread

    transcriber = StreamTranscriber(transcription_config, stream_config, gcs_config)
    # Eagerly load the model so all threads share one copy
    _ = transcriber._transcriber.model
    storage = get_storage(gcs_config)
    r = get_redis(redis_config)
    ch = _connect_clickhouse(ch_config)
    stop = Event()

    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    def _worker_loop(thread_id: int) -> None:
        log.info("transcription thread started", thread_id=thread_id)

        while not stop.is_set():
            task = dequeue_chunk(r, timeout=5)
            if task is None:
                continue

            try:
                if transcript_exists(ch, task.feed_id, str(task.chunk_ts)):
                    log.debug("skipping duplicate transcript", feed_id=task.feed_id, archive_ts=str(task.chunk_ts))
                    continue

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

        log.info("transcription thread stopped", thread_id=thread_id)

    log.info("transcription worker started", num_threads=num_threads)

    threads = []
    for i in range(num_threads):
        t = Thread(target=_worker_loop, args=(i,), name=f"transcriber-{i}", daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()


def run_processor(
    redis_config: RedisConfig,
    ch_config: ClickHouseConfig,
    nlp_config: GoogleNLPConfig,
    geocoding_config: GoogleGeocodingConfig,
    region_config: RegionConfig,
) -> None:
    r = get_redis(redis_config)
    ch = _connect_clickhouse(ch_config)
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
            surrounding = fetch_surrounding_context(ch, task.feed_id, str(task.chunk_ts))
            context_text = surrounding if surrounding else task.full_text

            entities = extract_entities(context_text, nlp_config, feed_id=task.feed_id)
            if not entities:
                entities = extract_clauses(context_text)

            events = []
            batch_coords: list[tuple[float, float]] = []
            for e in entities:
                result = geocoder.geocode(e, feed_name=task.feed_name, feed_id=task.feed_id)
                if result is None:
                    continue
                lat, lon, name = result
                if has_recent_event(ch, name, lat, lon, ref_ts=str(task.chunk_ts), minutes=10):
                    log.debug("skipping duplicate event", normalized=name)
                    continue
                too_close = any(
                    abs(lat - blat) < 0.005 and abs(lon - blon) < 0.005
                    for blat, blon in batch_coords
                )
                if too_close:
                    log.debug("skipping batch duplicate", normalized=name)
                    continue
                batch_coords.append((lat, lon))
                ctx = surrounding[:500] if surrounding else e.context
                events.append(GeocodedEvent(
                    feed_id=task.feed_id,
                    archive_ts=task.chunk_ts,
                    event_ts=task.chunk_ts,
                    raw_location=e.raw_text,
                    normalized=name,
                    latitude=lat,
                    longitude=lon,
                    confidence=e.confidence,
                    context=ctx,
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
