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
    `SELECT feed_id, archive_ts, event_ts, raw_location, normalized, ` +
    `latitude, longitude, confidence, context, tags ` +
    `FROM blotter.scanner_events ` +
    `WHERE event_ts BETWEEN fromUnixTimestamp(${startTs}) AND fromUnixTimestamp(${endTs})`;

  if (bounds) {
    sql +=
      ` AND longitude BETWEEN ${bounds.west} AND ${bounds.east}` +
      ` AND latitude BETWEEN ${bounds.south} AND ${bounds.north}`;
  }

  if (search) {
    const escaped = search.replace(/'/g, "\\'").replace(/%/g, "\\%").replace(/_/g, "\\_");
    sql +=
      ` AND (context ILIKE '%${escaped}%'` +
      ` OR normalized ILIKE '%${escaped}%'` +
      ` OR raw_location ILIKE '%${escaped}%'` +
      ` OR tags ILIKE '%${escaped}%')`;
  }

  sql += ` ORDER BY event_ts DESC LIMIT 5000`;
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
