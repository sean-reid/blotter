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
): Promise<ScannerEvent[]> {
  let sql =
    `SELECT feed_id, archive_ts, event_ts, raw_location, normalized, ` +
    `latitude, longitude, confidence ` +
    `FROM blotter.scanner_events ` +
    `WHERE event_ts BETWEEN fromUnixTimestamp(${startTs}) AND fromUnixTimestamp(${endTs})`;

  if (bounds) {
    sql +=
      ` AND longitude BETWEEN ${bounds.west} AND ${bounds.east}` +
      ` AND latitude BETWEEN ${bounds.south} AND ${bounds.north}`;
  }

  sql += ` ORDER BY event_ts DESC LIMIT 5000`;
  return query<ScannerEvent>(sql);
}

export async function searchTranscripts(
  term: string,
  startTs: number,
  endTs: number,
): Promise<TranscriptResult[]> {
  const escaped = term.replace(/'/g, "\\'");
  const sql =
    `SELECT feed_id, feed_name, archive_ts, duration_ms, audio_url, transcript ` +
    `FROM blotter.scanner_transcripts ` +
    `WHERE hasToken(transcript, '${escaped}') ` +
    `AND archive_ts BETWEEN fromUnixTimestamp(${startTs}) AND fromUnixTimestamp(${endTs}) ` +
    `ORDER BY archive_ts DESC LIMIT 100`;
  return query<TranscriptResult>(sql);
}
