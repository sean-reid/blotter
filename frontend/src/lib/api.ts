import type { ScannerEvent, TranscriptResult } from "./types";

const QUERY_URL = "/api/query";

async function query<T>(sql: string): Promise<T[]> {
  const resp = await fetch(QUERY_URL, {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: `${sql} FORMAT JSONEachRow`,
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
  let sql =
    `SELECT e.feed_id, e.archive_ts, e.event_ts, e.raw_location, e.normalized, ` +
    `e.latitude, e.longitude, e.confidence, e.context, e.tags ` +
    `FROM blotter.scanner_events e ` +
    `WHERE e.event_ts BETWEEN fromUnixTimestamp(${startTs}) AND fromUnixTimestamp(${endTs})`;

  if (bounds) {
    sql +=
      ` AND e.longitude BETWEEN ${bounds.west} AND ${bounds.east}` +
      ` AND e.latitude BETWEEN ${bounds.south} AND ${bounds.north}`;
  }

  if (search) {
    const escaped = search.replace(/'/g, "\\'").replace(/%/g, "\\%").replace(/_/g, "\\_");
    sql +=
      ` AND (e.context ILIKE '%${escaped}%'` +
      ` OR e.normalized ILIKE '%${escaped}%'` +
      ` OR e.raw_location ILIKE '%${escaped}%'` +
      ` OR e.tags ILIKE '%${escaped}%'` +
      ` OR EXISTS (SELECT 1 FROM blotter.scanner_transcripts t` +
      ` WHERE t.feed_id = e.feed_id` +
      ` AND abs(toInt64(t.archive_ts) - toInt64(toDateTime64(e.archive_ts, 3))) < 120` +
      ` AND (t.transcript ILIKE '%${escaped}%' OR t.tags ILIKE '%${escaped}%')))`;
  }

  sql += ` ORDER BY e.event_ts DESC LIMIT 5000`;
  return query<ScannerEvent>(sql);
}

export async function fetchTranscriptForEvent(
  feedId: string,
  archiveTs: string,
): Promise<TranscriptResult | null> {
  const escaped = feedId.replace(/'/g, "\\'");
  const sql =
    `SELECT feed_id, feed_name, archive_ts, duration_ms, audio_url, transcript, segments, tags ` +
    `FROM blotter.scanner_transcripts ` +
    `WHERE feed_id = '${escaped}' ` +
    `AND length(transcript) > 0 ` +
    `AND abs(toInt64(archive_ts) - toInt64(toDateTime64('${archiveTs}', 3))) < 120 ` +
    `ORDER BY abs(toInt64(archive_ts) - toInt64(toDateTime64('${archiveTs}', 3))) ASC ` +
    `LIMIT 1`;
  const results = await query<TranscriptResult>(sql);
  return results[0] ?? null;
}

export async function fetchEventForTranscript(
  feedId: string,
  archiveTs: string,
): Promise<ScannerEvent | null> {
  const escaped = feedId.replace(/'/g, "\\'");
  const sql =
    `SELECT feed_id, archive_ts, event_ts, raw_location, normalized, ` +
    `latitude, longitude, confidence, context, tags ` +
    `FROM blotter.scanner_events ` +
    `WHERE feed_id = '${escaped}' ` +
    `AND abs(toInt64(toDateTime64(archive_ts, 3)) - toInt64(toDateTime64('${archiveTs}', 3))) < 120 ` +
    `ORDER BY abs(toInt64(toDateTime64(archive_ts, 3)) - toInt64(toDateTime64('${archiveTs}', 3))) ASC ` +
    `LIMIT 1`;
  const results = await query<ScannerEvent>(sql);
  return results[0] ?? null;
}

export async function searchTranscripts(
  term: string,
  startTs: number,
  endTs: number,
): Promise<TranscriptResult[]> {
  let sql =
    `SELECT feed_id, feed_name, archive_ts, duration_ms, audio_url, transcript, segments, tags ` +
    `FROM blotter.scanner_transcripts ` +
    `WHERE length(transcript) > 0 ` +
    `AND archive_ts BETWEEN fromUnixTimestamp(${startTs}) AND fromUnixTimestamp(${endTs})`;

  if (term) {
    const escaped = term.replace(/'/g, "\\'").replace(/%/g, "\\%").replace(/_/g, "\\_");
    sql += ` AND (transcript ILIKE '%${escaped}%' OR tags ILIKE '%${escaped}%')`;
  }

  sql += ` ORDER BY archive_ts DESC LIMIT 50`;
  return query<TranscriptResult>(sql);
}
