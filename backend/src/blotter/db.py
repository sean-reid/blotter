import json

import psycopg
from psycopg.rows import dict_row

from blotter.config import PostgresConfig
from blotter.log import get_logger
from blotter.models import GeocodedEvent, Transcript
from blotter.stages.extract_codes import code_label

log = get_logger(__name__)


def get_conn(config: PostgresConfig) -> psycopg.Connection:
    return psycopg.connect(config.conninfo, autocommit=True)


def _tags_str(tags: list[str], feed_id: str = "") -> str:
    parts = []
    for tag in tags:
        label = code_label(tag, feed_id=feed_id)
        parts.append(f"{tag}:{label.replace(',', ' /')}" if label else tag)
    return ",".join(parts)


def insert_transcript(conn: psycopg.Connection, t: Transcript) -> None:
    segments_json = json.dumps([s.model_dump() for s in t.segments])
    tags_str = _tags_str(t.tags, feed_id=t.feed_id)
    conn.execute(
        """INSERT INTO scanner_transcripts
           (feed_id, feed_name, archive_ts, duration_ms, audio_url, transcript, segments, tags, window_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (feed_id, archive_ts) DO NOTHING""",
        (t.feed_id, t.feed_name, t.archive_ts, t.duration_ms,
         t.audio_url, t.full_text, segments_json, tags_str, t.window_id),
    )
    if t.embedding:
        conn.execute(
            """INSERT INTO transcript_embeddings (feed_id, archive_ts, embedding)
               VALUES (%s, %s, %s)
               ON CONFLICT (feed_id, archive_ts) DO NOTHING""",
            (t.feed_id, t.archive_ts, t.embedding),
        )
    log.info("inserted transcript", feed_id=t.feed_id, archive_ts=str(t.archive_ts), tags=tags_str)


def insert_events(conn: psycopg.Connection, events: list[GeocodedEvent]) -> None:
    if not events:
        return
    for e in events:
        tags_str = _tags_str(e.tags, feed_id=e.feed_id)
        conn.execute(
            """INSERT INTO scanner_events
               (feed_id, archive_ts, event_ts, raw_location, normalized,
                latitude, longitude, confidence, context, tags, window_id, summary)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (feed_id, archive_ts, normalized)
               DO UPDATE SET context = EXCLUDED.context, summary = EXCLUDED.summary,
                            created_at = now()""",
            (e.feed_id, e.archive_ts, e.event_ts, e.raw_location, e.normalized,
             e.latitude, e.longitude, e.confidence, e.context, tags_str,
             e.window_id, e.summary),
        )
    log.info("inserted events", count=len(events), feed_id=events[0].feed_id)


def has_recent_event(
    conn: psycopg.Connection,
    normalized: str,
    lat: float,
    lon: float,
    ref_ts: str,
    minutes: int = 10,
    radius_deg: float = 0.002,
) -> bool:
    row = conn.execute(
        """SELECT count(*) FROM scanner_events
           WHERE event_ts BETWEEN %s::timestamptz - make_interval(mins => %s)
                               AND %s::timestamptz + make_interval(mins => %s)
           AND (normalized = %s
                OR (abs(latitude - %s) < %s AND abs(longitude - %s) < %s))""",
        (ref_ts, minutes, ref_ts, minutes, normalized, lat, radius_deg, lon, radius_deg),
    ).fetchone()
    return row is not None and row[0] > 0


def fetch_surrounding_context(
    conn: psycopg.Connection,
    feed_id: str,
    archive_ts: str,
    window_minutes: int = 2,
    max_rows: int = 20,
) -> str:
    rows = conn.execute(
        """SELECT transcript FROM scanner_transcripts
           WHERE feed_id = %s
           AND archive_ts BETWEEN %s::timestamptz - make_interval(mins => %s)
                               AND %s::timestamptz + make_interval(mins => %s)
           AND length(transcript) > 0
           ORDER BY archive_ts ASC
           LIMIT %s""",
        (feed_id, archive_ts, window_minutes, archive_ts, window_minutes, max_rows),
    ).fetchall()
    texts = [r[0] for r in rows if r[0].strip()]
    return " /// ".join(texts)


def fetch_window_transcripts(
    conn: psycopg.Connection,
    window_id: str,
    max_rows: int = 30,
) -> str:
    rows = conn.execute(
        """SELECT transcript FROM scanner_transcripts
           WHERE window_id = %s
           AND length(transcript) > 0
           ORDER BY archive_ts ASC
           LIMIT %s""",
        (window_id, max_rows),
    ).fetchall()
    texts = [r[0] for r in rows if r[0].strip()]
    return " /// ".join(texts)


def transcript_exists(conn: psycopg.Connection, feed_id: str, archive_ts: str) -> bool:
    row = conn.execute(
        "SELECT count(*) FROM scanner_transcripts WHERE feed_id = %s AND archive_ts = %s::timestamptz",
        (feed_id, archive_ts),
    ).fetchone()
    return row is not None and row[0] > 0


def cleanup_old_rows(conn: psycopg.Connection, days: int = 7) -> None:
    for table, ts_col in [
        ("scanner_transcripts", "archive_ts"),
        ("scanner_events", "event_ts"),
        ("transcript_embeddings", "archive_ts"),
    ]:
        result = conn.execute(
            f"DELETE FROM {table} WHERE {ts_col} < now() - make_interval(days => %s)",  # noqa: S608
            (days,),
        )
        if result.rowcount:
            log.info("ttl cleanup", table=table, deleted=result.rowcount)
