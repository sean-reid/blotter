import signal
import time
from threading import Event

from blotter.config import (
    EmbeddingConfig, GCSConfig, GoogleGeocodingConfig, GoogleNLPConfig,
    OllamaConfig, OpenMhzConfig, PostgresConfig, RedisConfig, RegionConfig,
    StreamConfig, TranscriptionConfig,
)
from blotter.db import (
    fetch_surrounding_context, fetch_window_transcripts, get_conn,
    has_recent_event, insert_events, insert_transcript, transcript_exists,
)
from blotter.gcs import get_storage
from blotter.log import get_logger
from blotter.models import GeocodedEvent, Transcript, TranscriptTask
from blotter.queue import (
    dequeue_chunk, dequeue_transcript, enqueue_transcript, get_redis,
    queue_depth, CAPTURE_QUEUE,
)
from blotter.stages.capture import CaptureManager
from blotter.stages.capture_openmhz import OpenMhzCaptureManager
from blotter.stages.extract import extract_clauses
from blotter.stages.extract_codes import extract_codes
from blotter.stages.extract_nlp import extract_entities
from blotter.stages.geocode import Geocoder
from blotter.stages.stream_transcribe import StreamTranscriber

log = get_logger(__name__)


def _connect_postgres(pg_config: PostgresConfig, stop: Event | None = None, delay: int = 5):
    attempt = 0
    while True:
        attempt += 1
        try:
            conn = get_conn(pg_config)
            conn.execute("SELECT 1")
            if attempt > 1:
                log.info("postgres connected", after_attempts=attempt)
            return conn
        except Exception:
            if stop is not None and stop.is_set():
                raise
            log.warning("postgres not ready, retrying", attempt=attempt, delay=delay)
            if stop is not None:
                stop.wait(delay)
            else:
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
    pg_config: PostgresConfig,
    embedding_config: EmbeddingConfig | None = None,
    num_threads: int = 1,
) -> None:
    from threading import Thread

    transcriber = StreamTranscriber(transcription_config, stream_config, gcs_config)
    _ = transcriber._transcriber.model

    import faster_whisper.vad as _vad_mod
    _cached_vad = _vad_mod.get_vad_model()
    _vad_mod.get_vad_model = lambda: _cached_vad

    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    embedder = None
    if embedding_config and embedding_config.enabled:
        from blotter.stages.embed import Embedder
        embedder = Embedder(embedding_config)
    storage = get_storage(gcs_config)
    r = get_redis(redis_config)

    WINDOW_GAP_SECONDS = 60
    _last_seen: dict[str, tuple[float, str]] = {}

    import ctypes
    _libc = ctypes.CDLL("libc.so.6", use_errno=True)
    _malloc_trim = _libc.malloc_trim

    def _worker_loop(thread_id: int) -> None:
        conn = _connect_postgres(pg_config, stop)
        log.info("transcription thread started", thread_id=thread_id)
        processed = 0

        try:
            while not stop.is_set():
                task = dequeue_chunk(r, timeout=5)
                if task is None:
                    continue

                processed += 1
                if processed % 100 == 0:
                    _malloc_trim(0)

                try:
                    if transcript_exists(conn, task.feed_id, str(task.chunk_ts)):
                        log.debug("skipping duplicate transcript", feed_id=task.feed_id, archive_ts=str(task.chunk_ts))
                        continue

                    segments, full_text, actual_duration_ms = transcriber.process_chunk(task)

                    if not full_text:
                        try:
                            storage.delete(task.chunk_path)
                        except Exception:
                            log.debug("failed to delete empty chunk", chunk_path=task.chunk_path, exc_info=True)
                        continue

                    tags = extract_codes(full_text, feed_id=task.feed_id)
                    duration_ms = actual_duration_ms or task.duration_ms

                    chunk_epoch = task.chunk_ts.timestamp()
                    prev = _last_seen.get(task.feed_id)
                    if prev and (chunk_epoch - prev[0]) < WINDOW_GAP_SECONDS:
                        window_id = prev[1]
                    else:
                        window_id = f"{task.feed_id}_{task.chunk_ts.strftime('%Y%m%dT%H%M%S')}"
                    _last_seen[task.feed_id] = (chunk_epoch, window_id)

                    embedding: list[float] = []
                    if embedder:
                        try:
                            embedding = embedder.encode(full_text)
                        except Exception:
                            log.warning("embedding failed", feed_id=task.feed_id, exc_info=True)

                    transcript = Transcript(
                        feed_id=task.feed_id,
                        feed_name=task.feed_name,
                        archive_ts=task.chunk_ts,
                        duration_ms=duration_ms,
                        audio_url=task.audio_url,
                        segments=segments,
                        full_text=full_text,
                        tags=tags,
                        window_id=window_id,
                        embedding=embedding,
                    )
                    insert_transcript(conn, transcript)

                    tt = TranscriptTask(
                        feed_id=task.feed_id,
                        feed_name=task.feed_name,
                        chunk_ts=task.chunk_ts,
                        duration_ms=duration_ms,
                        audio_url=task.audio_url,
                        segments=segments,
                        full_text=full_text,
                        tags=tags,
                        window_id=window_id,
                    )
                    enqueue_transcript(r, tt)

                    depth = queue_depth(r, CAPTURE_QUEUE)
                    if depth > 50:
                        log.warning("transcription backlog", depth=depth)

                except Exception:
                    log.error("transcription failed", feed_id=task.feed_id, exc_info=True)
                    try:
                        conn.execute("SELECT 1")
                    except Exception:
                        log.warning("pg connection lost, reconnecting", thread_id=thread_id)
                        try:
                            conn.close()
                        except Exception:
                            pass
                        conn = _connect_postgres(pg_config, stop)
        finally:
            try:
                conn.close()
            except Exception:
                pass

        log.info("transcription thread stopped", thread_id=thread_id)

    log.info("transcription worker started", threads=num_threads)

    threads: list[Thread] = []
    for i in range(num_threads):
        t = Thread(target=_worker_loop, args=(i,), name=f"transcriber-{i}", daemon=True)
        t.start()
        threads.append(t)

    while not stop.is_set():
        stop.wait(30)

    for t in threads:
        t.join(timeout=10)


def run_processor(
    redis_config: RedisConfig,
    pg_config: PostgresConfig,
    nlp_config: GoogleNLPConfig,
    geocoding_config: GoogleGeocodingConfig,
    region_config: RegionConfig,
    ollama_config: OllamaConfig | None = None,
    num_threads: int = 2,
) -> None:
    import ctypes
    import gc
    import threading
    from threading import Lock, Thread

    r = get_redis(redis_config)
    geocoder = Geocoder(geocoding_config, region_config)

    try:
        _libc = ctypes.CDLL("libc.so.6", use_errno=True)
        _proc_malloc_trim = _libc.malloc_trim
    except Exception:
        _proc_malloc_trim = None

    summarizer = None
    if ollama_config and ollama_config.enabled:
        from blotter.stages.summarize import Summarizer
        summarizer = Summarizer(ollama_config)
        log.info("ollama summarizer enabled", model=ollama_config.model)

    stop = Event()
    _recent_events: set[str] = set()
    _recent_lock = Lock()

    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    def _claim_event(name: str, ts_epoch: float) -> bool:
        key = f"{name.lower()}|{int(ts_epoch // 600)}"
        with _recent_lock:
            if key in _recent_events:
                return False
            _recent_events.add(key)
            if len(_recent_events) > 5000:
                _recent_events.clear()
            return True

    def _processor_loop(thread_id: int) -> None:
        conn = _connect_postgres(pg_config, stop)
        log.info("processor thread started", thread_id=thread_id)
        processed = 0

        try:
            while not stop.is_set():
                task = dequeue_transcript(r, timeout=5)
                if task is None:
                    continue

                processed += 1
                if processed % 50 == 0:
                    gc.collect(1)
                    if _proc_malloc_trim:
                        _proc_malloc_trim(0)
                    tc = threading.active_count()
                    if tc > 10:
                        names: dict[str, int] = {}
                        for t in threading.enumerate():
                            names[t.name] = names.get(t.name, 0) + 1
                        log.warning("thread_audit", count=tc, names=names)

                try:
                    if task.window_id:
                        surrounding = fetch_window_transcripts(conn, task.window_id)
                    else:
                        surrounding = fetch_surrounding_context(conn, task.feed_id, str(task.chunk_ts))
                    context_text = surrounding if surrounding else task.full_text

                    if len(context_text) < 30:
                        continue

                    tags = extract_codes(context_text, feed_id=task.feed_id) if surrounding else task.tags

                    entities = extract_entities(context_text, nlp_config, feed_id=task.feed_id)
                    if not entities:
                        entities = extract_clauses(context_text)

                    summary = ""
                    if summarizer and len(context_text) > 100:
                        summary = summarizer.summarize(context_text) or ""

                    events = []
                    batch_coords: list[tuple[float, float]] = []
                    for e in entities:
                        result = geocoder.geocode(e, feed_name=task.feed_name, feed_id=task.feed_id)
                        if result is None:
                            continue
                        lat, lon, name = result
                        if not _claim_event(name, task.chunk_ts.timestamp()):
                            log.debug("skipping cross-thread duplicate", normalized=name)
                            continue
                        if has_recent_event(conn, name, lat, lon, ref_ts=str(task.chunk_ts), minutes=10):
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
                            tags=tags,
                            window_id=task.window_id,
                            summary=summary,
                        ))

                    insert_events(conn, events)
                    log.info(
                        "chunk processed",
                        feed_id=task.feed_id,
                        entities=len(entities),
                        events=len(events),
                    )

                except Exception:
                    log.error("processing failed", feed_id=task.feed_id, exc_info=True)
                    try:
                        conn.execute("SELECT 1")
                    except Exception:
                        log.warning("pg connection lost, reconnecting", thread_id=thread_id)
                        try:
                            conn.close()
                        except Exception:
                            pass
                        conn = _connect_postgres(pg_config, stop)
        finally:
            try:
                conn.close()
            except Exception:
                pass

        log.info("processor thread stopped", thread_id=thread_id)

    log.info("processing worker started", num_threads=num_threads)

    threads: list[Thread] = []
    for i in range(num_threads):
        t = Thread(target=_processor_loop, args=(i,), name=f"processor-{i}", daemon=True)
        t.start()
        threads.append(t)

    while not stop.is_set():
        stop.wait(10)

    for t in threads:
        t.join(timeout=10)
