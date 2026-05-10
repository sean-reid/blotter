import typer

from blotter.config import get_settings
from blotter.log import get_logger

app = typer.Typer(name="blotter", help="Police scanner archive search pipeline")
log = get_logger(__name__)


@app.command()
def extract(feed_id: str) -> None:
    """Extract locations and geocode for a feed's transcripts."""
    settings = get_settings()
    from blotter.db import get_conn, insert_events
    from blotter.models import GeocodedEvent
    from blotter.stages.extract import extract_clauses
    from blotter.stages.extract_nlp import extract_entities
    from blotter.stages.geocode import Geocoder

    conn = get_conn(settings.postgres)
    geocoder = Geocoder(settings.google_geocoding, settings.region)

    rows = conn.execute(
        """SELECT feed_id, archive_ts, transcript FROM scanner_transcripts
           WHERE feed_id = %s
           AND (feed_id, archive_ts) NOT IN
           (SELECT feed_id, archive_ts FROM scanner_events)""",
        (feed_id,),
    ).fetchall()

    for row in rows:
        fid, archive_ts, transcript = row
        nlp_entities = extract_entities(transcript, settings.google_nlp, feed_id=fid)
        clauses = nlp_entities if nlp_entities else extract_clauses(transcript)
        events: list[GeocodedEvent] = []
        for clause in clauses:
            result = geocoder.geocode(clause)
            if result is None:
                continue
            lat, lon, resolved_name = result
            events.append(GeocodedEvent(
                feed_id=fid,
                archive_ts=archive_ts,
                event_ts=archive_ts,
                raw_location=clause.raw_text,
                normalized=resolved_name,
                latitude=lat,
                longitude=lon,
                confidence=0.8,
                context=clause.context,
            ))
        insert_events(conn, events)
        typer.echo(f"extracted: {archive_ts} -> {len(events)} events")


stream_app = typer.Typer(name="stream", help="Real-time stream capture and processing")
app.add_typer(stream_app)


@stream_app.command("start")
def stream_start(
    capture: bool = typer.Option(True, help="Run capture workers"),
    transcribe_worker: bool = typer.Option(True, "--transcribe", help="Run transcription worker"),
    transcriber_workers: int = typer.Option(1, "--transcriber-workers", help="Number of transcription workers"),
    process: bool = typer.Option(True, help="Run processing worker"),
) -> None:
    """Start real-time stream capture and processing."""
    import multiprocessing
    import signal

    settings = get_settings()
    procs: list[multiprocessing.Process] = []

    if capture:
        from blotter.stages.worker import run_capture_openmhz
        p = multiprocessing.Process(
            target=run_capture_openmhz,
            args=(settings.openmhz, settings.gcs, settings.redis),
            name="capture",
        )
        procs.append(p)

    if transcribe_worker:
        from blotter.stages.worker import run_transcriber
        p = multiprocessing.Process(
            target=run_transcriber,
            args=(settings.transcription, settings.stream, settings.gcs, settings.redis, settings.postgres, settings.embedding, transcriber_workers),
            name="transcriber",
        )
        procs.append(p)

    if process:
        from blotter.stages.worker import run_processor
        p = multiprocessing.Process(
            target=run_processor,
            args=(settings.redis, settings.postgres, settings.google_nlp, settings.google_geocoding, settings.region, settings.ollama),
            name="processor",
        )
        procs.append(p)

    def _shutdown(*_):
        for p in procs:
            p.terminate()
        for p in procs:
            p.join(timeout=10)
            if p.is_alive():
                p.kill()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown)

    for p in procs:
        p.start()
        log.info("started worker", name=p.name, pid=p.pid)

    typer.echo(f"Started {len(procs)} workers. Press Ctrl+C to stop.")

    try:
        for p in procs:
            p.join()
    except KeyboardInterrupt:
        _shutdown()


@stream_app.command("status")
def stream_status() -> None:
    """Show stream capture status."""
    settings = get_settings()
    from blotter.queue import get_redis, queue_depth, CAPTURE_QUEUE, TRANSCRIPT_QUEUE

    r = get_redis(settings.redis)
    try:
        r.ping()
        typer.echo("Redis: connected")
    except Exception:
        typer.echo("Redis: not reachable")
        raise typer.Exit(1)

    typer.echo(f"Capture queue depth: {queue_depth(r, CAPTURE_QUEUE)}")
    typer.echo(f"Transcript queue depth: {queue_depth(r, TRANSCRIPT_QUEUE)}")

    systems = [s.strip() for s in settings.openmhz.systems.split(",") if s.strip()]
    typer.echo(f"\nConfigured OpenMHz systems ({len(systems)}):")
    for sys_name in systems:
        typer.echo(f"  {sys_name}")


if __name__ == "__main__":
    app()
