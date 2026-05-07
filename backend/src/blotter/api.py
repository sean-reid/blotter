import json
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from blotter.config import PostgresConfig

_pool: psycopg.Connection | None = None


def _conn() -> psycopg.Connection:
    global _pool
    if _pool is None or _pool.closed:
        from blotter.config import get_settings
        cfg = get_settings().postgres
        _pool = psycopg.connect(cfg.conninfo, autocommit=True, row_factory=dict_row)
    return _pool


def _ts_from_unix(val: str) -> datetime:
    return datetime.fromtimestamp(int(val), tz=timezone.utc)


async def events(request: Request) -> JSONResponse:
    p = request.query_params
    start_ts = _ts_from_unix(p["startTs"])
    end_ts = _ts_from_unix(p["endTs"])

    params: list = [start_ts, end_ts]
    where = ["event_ts BETWEEN %s AND %s"]

    if "west" in p:
        where.append("longitude BETWEEN %s AND %s")
        params.extend([float(p["west"]), float(p["east"])])
        where.append("latitude BETWEEN %s AND %s")
        params.extend([float(p["south"]), float(p["north"])])

    if "search" in p:
        term = f"%{p['search']}%"
        where.append(
            "(context ILIKE %s OR normalized ILIKE %s OR raw_location ILIKE %s"
            " OR tags ILIKE %s OR feed_id ILIKE %s OR summary ILIKE %s)"
        )
        params.extend([term] * 6)

    sql = (
        "SELECT DISTINCT ON (feed_id, archive_ts)"
        " feed_id, archive_ts, event_ts, raw_location, normalized,"
        " latitude, longitude, confidence, context, tags, window_id, summary"
        " FROM scanner_events"
        f" WHERE {' AND '.join(where)}"
        " ORDER BY feed_id, archive_ts, created_at DESC"
        " LIMIT 5000"
    )
    rows = _conn().execute(sql, params).fetchall()
    for r in rows:
        r["archive_ts"] = r["archive_ts"].isoformat()
        r["event_ts"] = r["event_ts"].isoformat()
    return JSONResponse(rows)


async def transcript_for_event(request: Request) -> JSONResponse:
    p = request.query_params
    rows = _conn().execute(
        """SELECT feed_id, feed_name, archive_ts, duration_ms, audio_url,
                  transcript, segments, tags, '' AS context
           FROM scanner_transcripts
           WHERE feed_id = %s AND length(transcript) > 0
           AND abs(extract(epoch from archive_ts - %s::timestamptz)) < 120
           ORDER BY abs(extract(epoch from archive_ts - %s::timestamptz)) ASC
           LIMIT 1""",
        (p["feedId"], p["archiveTs"], p["archiveTs"]),
    ).fetchall()
    if not rows:
        return JSONResponse(None)
    r = rows[0]
    r["archive_ts"] = r["archive_ts"].isoformat()
    return JSONResponse(r)


async def surrounding_transcripts(request: Request) -> JSONResponse:
    p = request.query_params
    window = int(p.get("window", "2"))
    rows = _conn().execute(
        """SELECT feed_id, feed_name, archive_ts, duration_ms, audio_url,
                  transcript, segments, tags, '' AS context
           FROM scanner_transcripts
           WHERE feed_id = %s AND length(transcript) > 0
           AND archive_ts BETWEEN %s::timestamptz - make_interval(mins => %s)
                               AND %s::timestamptz + make_interval(mins => %s)
           ORDER BY archive_ts ASC LIMIT 20""",
        (p["feedId"], p["archiveTs"], window, p["archiveTs"], window),
    ).fetchall()
    for r in rows:
        r["archive_ts"] = r["archive_ts"].isoformat()
    return JSONResponse(rows)


async def street_filtered_transcripts(request: Request) -> JSONResponse:
    p = request.query_params
    window = int(p.get("window", "10"))
    rows = _conn().execute(
        """SELECT feed_id, feed_name, archive_ts, duration_ms, audio_url,
                  transcript, segments, tags, '' AS context
           FROM scanner_transcripts
           WHERE feed_id = %s AND length(transcript) > 0
           AND archive_ts BETWEEN %s::timestamptz - make_interval(mins => %s)
                               AND %s::timestamptz + make_interval(mins => %s)
           AND transcript ILIKE %s
           ORDER BY archive_ts ASC LIMIT 20""",
        (p["feedId"], p["archiveTs"], window, p["archiveTs"], window,
         f"%{p['street']}%"),
    ).fetchall()
    for r in rows:
        r["archive_ts"] = r["archive_ts"].isoformat()
    return JSONResponse(rows)


async def incident_transcripts(request: Request) -> JSONResponse:
    p = request.query_params
    rows = _conn().execute(
        """SELECT feed_id, feed_name, archive_ts, duration_ms, audio_url,
                  transcript, segments, tags, '' AS context
           FROM scanner_transcripts
           WHERE window_id = %s AND length(transcript) > 0
           ORDER BY archive_ts ASC LIMIT 30""",
        (p["windowId"],),
    ).fetchall()
    for r in rows:
        r["archive_ts"] = r["archive_ts"].isoformat()
    return JSONResponse(rows)


async def event_for_transcript(request: Request) -> JSONResponse:
    p = request.query_params
    rows = _conn().execute(
        """SELECT feed_id, archive_ts, event_ts, raw_location, normalized,
                  latitude, longitude, confidence, context, tags, window_id, summary
           FROM scanner_events
           WHERE feed_id = %s
           AND abs(extract(epoch from archive_ts - %s::timestamptz)) < 120
           ORDER BY abs(extract(epoch from archive_ts - %s::timestamptz)) ASC
           LIMIT 1""",
        (p["feedId"], p["archiveTs"], p["archiveTs"]),
    ).fetchall()
    if not rows:
        return JSONResponse(None)
    r = rows[0]
    r["archive_ts"] = r["archive_ts"].isoformat()
    r["event_ts"] = r["event_ts"].isoformat()
    return JSONResponse(r)


async def related_events(request: Request) -> JSONResponse:
    p = request.query_params
    lat, lon = float(p["lat"]), float(p["lon"])
    rows = _conn().execute(
        """SELECT DISTINCT feed_id, event_ts, normalized, window_id, summary
           FROM scanner_events
           WHERE abs(latitude - %s) < 0.003 AND abs(longitude - %s) < 0.003
           AND event_ts BETWEEN %s::timestamptz - interval '30 minutes'
                           AND %s::timestamptz + interval '30 minutes'
           AND feed_id != %s
           ORDER BY event_ts ASC LIMIT 10""",
        (lat, lon, p["eventTs"], p["eventTs"], p["feedId"]),
    ).fetchall()
    for r in rows:
        r["event_ts"] = r["event_ts"].isoformat()
    return JSONResponse(rows)


async def search_transcripts(request: Request) -> JSONResponse:
    p = request.query_params
    start_ts = _ts_from_unix(p["startTs"])
    end_ts = _ts_from_unix(p["endTs"])
    term = p.get("term", "")

    params: list = [start_ts, end_ts]
    search_filter = ""
    context_expr = "'' AS context"

    if term:
        like = f"%{term}%"
        search_filter = (
            " AND (transcript ILIKE %s OR tags ILIKE %s"
            " OR feed_id ILIKE %s OR feed_name ILIKE %s)"
        )
        params.extend([like] * 4)
        context_expr = (
            "substring(transcript from greatest(1, position(lower(%s) in lower(transcript)) - 120)"
            " for length(%s) + 240) AS context"
        )
        params = [term, term] + params  # context_expr params come first in SELECT

    sql = (
        f"SELECT feed_id, feed_name, archive_ts, duration_ms, audio_url,"
        f" transcript, segments, tags, {context_expr}"
        f" FROM scanner_transcripts"
        f" WHERE length(transcript) > 0"
        f" AND archive_ts BETWEEN %s AND %s"
        f"{search_filter}"
        f" ORDER BY archive_ts DESC LIMIT 50"
    )
    rows = _conn().execute(sql, params).fetchall()
    for r in rows:
        r["archive_ts"] = r["archive_ts"].isoformat()
    return JSONResponse(rows)


async def health(request: Request) -> JSONResponse:
    row = _conn().execute(
        "SELECT count(*) AS c FROM scanner_transcripts WHERE created_at > now() - interval '20 minutes'"
    ).fetchone()
    count = row["c"] if row else 0
    return JSONResponse({"status": "ok" if count > 0 else "down", "transcripts_20min": count})


app = Starlette(routes=[
    Route("/api/events", events),
    Route("/api/transcripts/for-event", transcript_for_event),
    Route("/api/transcripts/surrounding", surrounding_transcripts),
    Route("/api/transcripts/street-filter", street_filtered_transcripts),
    Route("/api/transcripts/incident", incident_transcripts),
    Route("/api/events/for-transcript", event_for_transcript),
    Route("/api/events/related", related_events),
    Route("/api/transcripts/search", search_transcripts),
    Route("/api/health", health),
])
