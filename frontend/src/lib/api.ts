import type { RelatedFeedEvent, ScannerEvent, TranscriptResult } from "./types";

const API_BASE = import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? "https://api.blotter.fm" : "");

async function get<T>(path: string, params: Record<string, string>): Promise<T> {
  const url = new URL(path, API_BASE || window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  const resp = await fetch(url.toString());
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status} ${await resp.text()}`);
  }
  return resp.json();
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
  if (bounds) {
    params.west = String(bounds.west);
    params.east = String(bounds.east);
    params.south = String(bounds.south);
    params.north = String(bounds.north);
  }
  if (search) {
    params.search = search;
  }
  return get<ScannerEvent[]>("/api/events", params);
}

export async function fetchTranscriptForEvent(
  feedId: string,
  archiveTs: string,
): Promise<TranscriptResult | null> {
  return get<TranscriptResult | null>("/api/transcripts/for-event", {
    feedId,
    archiveTs,
  });
}

export async function fetchSurroundingTranscripts(
  feedId: string,
  archiveTs: string,
  windowMinutes: number = 2,
): Promise<TranscriptResult[]> {
  return get<TranscriptResult[]>("/api/transcripts/surrounding", {
    feedId,
    archiveTs,
    window: String(windowMinutes),
  });
}

export async function fetchStreetFilteredTranscripts(
  feedId: string,
  archiveTs: string,
  streetName: string,
  windowMinutes: number = 10,
): Promise<TranscriptResult[]> {
  return get<TranscriptResult[]>("/api/transcripts/street-filter", {
    feedId,
    archiveTs,
    street: streetName,
    window: String(windowMinutes),
  });
}

export async function fetchIncidentTranscripts(
  windowId: string,
): Promise<TranscriptResult[]> {
  return get<TranscriptResult[]>("/api/transcripts/incident", { windowId });
}

export async function fetchEventForTranscript(
  feedId: string,
  archiveTs: string,
): Promise<ScannerEvent | null> {
  return get<ScannerEvent | null>("/api/events/for-transcript", {
    feedId,
    archiveTs,
  });
}

export async function fetchRelatedEvents(
  feedId: string,
  eventTs: string,
  latitude: number,
  longitude: number,
): Promise<RelatedFeedEvent[]> {
  return get<RelatedFeedEvent[]>("/api/events/related", {
    feedId,
    eventTs,
    lat: String(latitude),
    lon: String(longitude),
  });
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
  if (term) {
    params.term = term;
  }
  return get<TranscriptResult[]>("/api/transcripts/search", params);
}
