import type { ScannerEvent, TranscriptResult } from "./types";

const QUERY_URL = "/api/query";

async function query<T>(sql: string, params?: Record<string, string>): Promise<T[]> {
  const url = new URL(QUERY_URL, window.location.origin);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      url.searchParams.set(`param_${key}`, value);
    }
  }

  const resp = await fetch(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: sql,
  });
  if (!resp.ok) {
    throw new Error(`Query failed: ${resp.status} ${await resp.text()}`);
  }
  const text = await resp.text();
  if (!text.trim()) return [];
  return text
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line) as T);
}

export async function fetchEvents(
  startTs: number,
  endTs: number,
  bounds?: { west: number; south: number; east: number; north: number },
  search?: string,
): Promise<ScannerEvent[]> {
  const params: Record<string, string> = {
    startTs: String(startTs),
    endTs: String(endTs),
  };

  let sql =
    `SELECT feed_id, archive_ts, event_ts, raw_location, normalized, ` +
    `latitude, longitude, confidence, context, tags ` +
    `FROM blotter.scanner_events FINAL ` +
    `WHERE event_ts BETWEEN fromUnixTimestamp({startTs:UInt64}) AND fromUnixTimestamp({endTs:UInt64})`;

  if (bounds) {
    params.west = String(bounds.west);
    params.east = String(bounds.east);
    params.south = String(bounds.south);
    params.north = String(bounds.north);
    sql +=
      ` AND longitude BETWEEN {west:Float64} AND {east:Float64}` +
      ` AND latitude BETWEEN {south:Float64} AND {north:Float64}`;
  }

  if (search) {
    params.search = `%${search}%`;
    sql +=
      ` AND (context ILIKE {search:String}` +
      ` OR normalized ILIKE {search:String}` +
      ` OR raw_location ILIKE {search:String}` +
      ` OR tags ILIKE {search:String}` +
      ` OR feed_id ILIKE {search:String})`;
  }

  sql += ` ORDER BY event_ts DESC LIMIT 1 BY feed_id, archive_ts LIMIT 5000`;
  return query<ScannerEvent>(sql, params);
}

export async function fetchTranscriptForEvent(
  feedId: string,
  archiveTs: string,
): Promise<TranscriptResult | null> {
  const sql =
    `SELECT feed_id, feed_name, archive_ts, duration_ms, audio_url, transcript, segments, tags, '' AS context ` +
    `FROM blotter.scanner_transcripts ` +
    `WHERE feed_id = {feedId:String} ` +
    `AND length(transcript) > 0 ` +
    `AND abs(toInt64(archive_ts) - toInt64(toDateTime64({archiveTs:String}, 3))) < 120 ` +
    `ORDER BY abs(toInt64(archive_ts) - toInt64(toDateTime64({archiveTs:String}, 3))) ASC ` +
    `LIMIT 1`;
  const results = await query<TranscriptResult>(sql, { feedId, archiveTs });
  return results[0] ?? null;
}

export async function fetchSurroundingTranscripts(
  feedId: string,
  archiveTs: string,
  windowMinutes: number = 2,
): Promise<TranscriptResult[]> {
  const sql =
    `SELECT feed_id, feed_name, archive_ts, duration_ms, audio_url, transcript, segments, tags, '' AS context ` +
    `FROM blotter.scanner_transcripts ` +
    `WHERE feed_id = {feedId:String} ` +
    `AND length(transcript) > 0 ` +
    `AND archive_ts BETWEEN toDateTime64({archiveTs:String}, 3) - INTERVAL {window:UInt32} MINUTE ` +
    `AND toDateTime64({archiveTs:String}, 3) + INTERVAL {window:UInt32} MINUTE ` +
    `ORDER BY archive_ts ASC ` +
    `LIMIT 20`;
  return query<TranscriptResult>(sql, { feedId, archiveTs, window: String(windowMinutes) });
}

export async function fetchEventForTranscript(
  feedId: string,
  archiveTs: string,
): Promise<ScannerEvent | null> {
  const sql =
    `SELECT feed_id, archive_ts, event_ts, raw_location, normalized, ` +
    `latitude, longitude, confidence, context, tags ` +
    `FROM blotter.scanner_events FINAL ` +
    `WHERE feed_id = {feedId:String} ` +
    `AND abs(toInt64(toDateTime64(archive_ts, 3)) - toInt64(toDateTime64({archiveTs:String}, 3))) < 120 ` +
    `ORDER BY abs(toInt64(toDateTime64(archive_ts, 3)) - toInt64(toDateTime64({archiveTs:String}, 3))) ASC ` +
    `LIMIT 1`;
  const results = await query<ScannerEvent>(sql, { feedId, archiveTs });
  return results[0] ?? null;
}

export async function searchTranscripts(
  term: string,
  startTs: number,
  endTs: number,
): Promise<TranscriptResult[]> {
  const params: Record<string, string> = {
    startTs: String(startTs),
    endTs: String(endTs),
  };

  const hasSearch = !!term;

  let contextExpr: string;
  if (hasSearch) {
    params.search = `%${term}%`;
    params.searchRaw = term;
    contextExpr = `substring(transcript, greatest(1, positionCaseInsensitive(transcript, {searchRaw:String}) - 120), length({searchRaw:String}) + 240) AS context`;
  } else {
    contextExpr = `'' AS context`;
  }

  let sql =
    `SELECT feed_id, feed_name, archive_ts, duration_ms, audio_url, transcript, segments, tags, ${contextExpr} ` +
    `FROM blotter.scanner_transcripts ` +
    `WHERE length(transcript) > 0 ` +
    `AND archive_ts BETWEEN fromUnixTimestamp({startTs:UInt64}) AND fromUnixTimestamp({endTs:UInt64})`;

  if (hasSearch) {
    sql += ` AND (transcript ILIKE {search:String} OR tags ILIKE {search:String} OR feed_id ILIKE {search:String} OR feed_name ILIKE {search:String})`;
  }

  sql += ` ORDER BY archive_ts DESC LIMIT 50`;
  return query<TranscriptResult>(sql, params);
}
