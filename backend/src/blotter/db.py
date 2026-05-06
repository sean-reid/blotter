import clickhouse_connect
from clickhouse_connect.driver import Client

from blotter.config import ClickHouseConfig
from blotter.log import get_logger
from blotter.models import GeocodedEvent, Transcript
from blotter.stages.extract_codes import code_label

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
    import json
    segments_json = json.dumps([s.model_dump() for s in t.segments])
    tag_parts = []
    for tag in t.tags:
        label = code_label(tag)
        tag_parts.append(f"{tag}:{label}" if label else tag)
    tags_str = ",".join(tag_parts)
    client.insert(
        "scanner_transcripts",
        [[
            t.feed_id,
            t.feed_name,
            t.archive_ts,
            t.duration_ms,
            t.audio_url,
            t.full_text,
            segments_json,
            tags_str,
            t.window_id,
            t.embedding,
        ]],
        column_names=[
            "feed_id",
            "feed_name",
            "archive_ts",
            "duration_ms",
            "audio_url",
            "transcript",
            "segments",
            "tags",
            "window_id",
            "embedding",
        ],
    )
    log.info("inserted transcript", feed_id=t.feed_id, archive_ts=str(t.archive_ts), tags=tags_str)


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
            e.context,
            ",".join(f"{t}:{code_label(t)}" if code_label(t) else t for t in e.tags),
            e.window_id,
            e.summary,
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
            "context",
            "tags",
            "window_id",
            "summary",
        ],
    )
    log.info("inserted events", count=len(events), feed_id=events[0].feed_id)


def has_recent_event(
    client: Client,
    normalized: str,
    lat: float,
    lon: float,
    ref_ts: str,
    minutes: int = 10,
    radius_deg: float = 0.002,
) -> bool:
    ts_clean = ref_ts.replace("+00:00", "").replace("Z", "")
    result = client.query(
        "SELECT count() FROM scanner_events "
        "WHERE event_ts BETWEEN toDateTime64({ts:String}, 3) - INTERVAL {minutes:UInt32} MINUTE "
        "AND toDateTime64({ts:String}, 3) + INTERVAL {minutes:UInt32} MINUTE "
        "AND (normalized = {normalized:String} "
        "  OR (abs(latitude - {lat:Float64}) < {radius:Float64} "
        "      AND abs(longitude - {lon:Float64}) < {radius:Float64}))",
        parameters={
            "normalized": normalized,
            "minutes": minutes,
            "lat": lat,
            "lon": lon,
            "radius": radius_deg,
            "ts": ts_clean,
        },
    )
    return result.first_row[0] > 0


def fetch_surrounding_context(
    client: Client,
    feed_id: str,
    archive_ts: str,
    window_minutes: int = 2,
    max_rows: int = 20,
) -> str:
    ts_clean = archive_ts.replace("+00:00", "").replace("Z", "")
    result = client.query(
        "SELECT transcript FROM scanner_transcripts "
        "WHERE feed_id = {feed_id:String} "
        "AND archive_ts BETWEEN toDateTime64({ts:String}, 3) - INTERVAL {window:UInt32} MINUTE "
        "AND toDateTime64({ts:String}, 3) + INTERVAL {window:UInt32} MINUTE "
        "AND length(transcript) > 0 "
        "ORDER BY archive_ts ASC "
        "LIMIT {limit:UInt32}",
        parameters={
            "feed_id": feed_id,
            "ts": ts_clean,
            "window": window_minutes,
            "limit": max_rows,
        },
    )
    texts = [row[0] for row in result.result_rows if row[0].strip()]
    return " /// ".join(texts)


def fetch_window_transcripts(
    client: Client,
    window_id: str,
    max_rows: int = 30,
) -> str:
    result = client.query(
        "SELECT transcript FROM scanner_transcripts "
        "WHERE window_id = {window_id:String} "
        "AND length(transcript) > 0 "
        "ORDER BY archive_ts ASC "
        "LIMIT {limit:UInt32}",
        parameters={
            "window_id": window_id,
            "limit": max_rows,
        },
    )
    texts = [row[0] for row in result.result_rows if row[0].strip()]
    return " /// ".join(texts)


def get_latest_transcript(client: Client, feed_id: str) -> dict | None:
    result = client.query(
        "SELECT archive_ts, transcript, segments, audio_url "
        "FROM scanner_transcripts "
        "WHERE feed_id = {feed_id:String} "
        "ORDER BY archive_ts DESC LIMIT 1",
        parameters={"feed_id": feed_id},
    )
    if not result.result_rows:
        return None
    row = result.result_rows[0]
    return {
        "archive_ts": row[0],
        "transcript": row[1],
        "segments": row[2],
        "audio_url": row[3],
    }


def transcript_exists(client: Client, feed_id: str, archive_ts: str) -> bool:
    ts_clean = archive_ts.replace("+00:00", "").replace("Z", "")
    result = client.query(
        "SELECT count() FROM scanner_transcripts WHERE feed_id = {feed_id:String} AND archive_ts = {archive_ts:String}",
        parameters={"feed_id": feed_id, "archive_ts": ts_clean},
    )
    return result.first_row[0] > 0
