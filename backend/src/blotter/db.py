import clickhouse_connect
from clickhouse_connect.driver import Client

from blotter.config import ClickHouseConfig
from blotter.log import get_logger
from blotter.models import GeocodedEvent, Transcript

log = get_logger(__name__)


def get_client(config: ClickHouseConfig) -> Client:
    return clickhouse_connect.get_client(
        host=config.host,
        port=config.port,
        database=config.database,
        username=config.username,
        password=config.password,
    )


def insert_transcript(client: Client, t: Transcript) -> None:
    client.insert(
        "scanner_transcripts",
        [[
            t.feed_id,
            t.feed_name,
            t.archive_ts,
            t.duration_ms,
            t.audio_url,
            t.full_text,
        ]],
        column_names=[
            "feed_id",
            "feed_name",
            "archive_ts",
            "duration_ms",
            "audio_url",
            "transcript",
        ],
    )
    log.info("inserted transcript", feed_id=t.feed_id, archive_ts=str(t.archive_ts))


def insert_events(client: Client, events: list[GeocodedEvent]) -> None:
    if not events:
        return
    rows = [
        [
            e.feed_id,
            e.archive_ts,
            e.event_ts,
            e.raw_location,
            e.normalized,
            e.latitude,
            e.longitude,
            e.confidence,
        ]
        for e in events
    ]
    client.insert(
        "scanner_events",
        rows,
        column_names=[
            "feed_id",
            "archive_ts",
            "event_ts",
            "raw_location",
            "normalized",
            "latitude",
            "longitude",
            "confidence",
        ],
    )
    log.info("inserted events", count=len(events), feed_id=events[0].feed_id)


def transcript_exists(client: Client, feed_id: str, archive_ts: str) -> bool:
    result = client.query(
        "SELECT count() FROM scanner_transcripts WHERE feed_id = {feed_id:String} AND archive_ts = {archive_ts:String}",
        parameters={"feed_id": feed_id, "archive_ts": archive_ts},
    )
    return result.first_row[0] > 0
