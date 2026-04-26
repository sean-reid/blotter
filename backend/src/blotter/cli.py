from datetime import datetime, timezone

import typer

from blotter.config import get_settings
from blotter.log import get_logger

app = typer.Typer(name="blotter", help="Police scanner archive search pipeline")
log = get_logger(__name__)


@app.command()
def fetch(feed_id: str) -> None:
    """Fetch archive listings for a feed."""
    settings = get_settings()
    from blotter.stages.fetch import BroadcastifyClient

    bc = BroadcastifyClient(settings.broadcastify)
    try:
        blocks = bc.get_archives(feed_id)
        for b in blocks:
            typer.echo(f"{b.timestamp.isoformat()}  {b.duration_ms}ms  {b.url}")
    finally:
        bc.close()


@app.command()
def download(feed_id: str) -> None:
    """Download and convert audio for a feed."""
    settings = get_settings()
    from blotter.stages.download import AudioDownloader
    from blotter.stages.fetch import BroadcastifyClient

    bc = BroadcastifyClient(settings.broadcastify)
    dl = AudioDownloader(settings.broadcastify, settings.data_dir)
    try:
        blocks = bc.get_archives(feed_id)
        for block in blocks:
            path = dl.download_and_convert(block)
            typer.echo(f"ready: {path}")
    finally:
        bc.close()
        dl.close()


@app.command()
def transcribe(feed_id: str) -> None:
    """Transcribe pending audio for a feed."""
    settings = get_settings()
    from blotter.db import get_client, insert_transcript, transcript_exists
    from blotter.models import Transcript
    from blotter.stages.download import AudioDownloader
    from blotter.stages.fetch import BroadcastifyClient
    from blotter.stages.transcribe import Transcriber

    bc = BroadcastifyClient(settings.broadcastify)
    dl = AudioDownloader(settings.broadcastify, settings.data_dir)
    tr = Transcriber(settings.transcription)
    client = get_client(settings.clickhouse)

    try:
        blocks = bc.get_archives(feed_id)
        for block in blocks:
            ts_str = block.timestamp.isoformat()
            if transcript_exists(client, feed_id, ts_str):
                log.info("already transcribed", ts=ts_str)
                continue

            wav = dl.download_and_convert(block)
            segments, full_text = tr.transcribe(wav)

            t = Transcript(
                feed_id=block.feed_id,
                feed_name=block.feed_name,
                archive_ts=block.timestamp,
                duration_ms=block.duration_ms,
                audio_url=block.url,
                segments=segments,
                full_text=full_text,
            )
            insert_transcript(client, t)
            typer.echo(f"transcribed: {ts_str} ({len(segments)} segments)")
    finally:
        bc.close()
        dl.close()


@app.command()
def extract(feed_id: str) -> None:
    """Extract locations and geocode for a feed's transcripts."""
    settings = get_settings()
    from blotter.db import get_client, insert_events
    from blotter.models import GeocodedEvent
    from blotter.stages.extract import extract_locations
    from blotter.stages.geocode import Geocoder

    client = get_client(settings.clickhouse)
    geocoder = Geocoder(settings.nominatim)

    rows = client.query(
        "SELECT feed_id, archive_ts, transcript FROM blotter.scanner_transcripts "
        "WHERE feed_id = {feed_id:String} "
        "AND (feed_id, archive_ts) NOT IN "
        "(SELECT feed_id, archive_ts FROM blotter.scanner_events)",
        parameters={"feed_id": feed_id},
    )

    for row in rows.result_rows:
        fid, archive_ts, transcript = row
        locations = extract_locations(transcript)
        events: list[GeocodedEvent] = []
        for loc in locations:
            coords = geocoder.geocode(loc)
            if coords is None:
                continue
            events.append(GeocodedEvent(
                feed_id=fid,
                archive_ts=archive_ts,
                event_ts=archive_ts,
                raw_location=loc.raw_text,
                normalized=loc.normalized,
                latitude=coords[0],
                longitude=coords[1],
                confidence=loc.confidence,
            ))
        insert_events(client, events)
        typer.echo(f"extracted: {archive_ts} -> {len(events)} events")


@app.command()
def run(feed_id: str) -> None:
    """Run full pipeline for a feed."""
    settings = get_settings()
    from blotter.stages.ingest import run_pipeline
    run_pipeline(settings, feed_id)


@app.command()
def run_all() -> None:
    """Run full pipeline for all configured feeds."""
    settings = get_settings()
    from blotter.stages.ingest import run_pipeline

    if not settings.feed_ids:
        typer.echo("No feed_ids configured. Set FEED_IDS env var.")
        raise typer.Exit(1)

    for feed_id in settings.feed_ids:
        log.info("starting feed", feed_id=feed_id)
        run_pipeline(settings, feed_id)


if __name__ == "__main__":
    app()
