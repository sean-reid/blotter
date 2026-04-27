import * as chrono from "chrono-node";
import type { TimeRange } from "./types";

interface ParseResult {
  cleanQuery: string;
  timeRange: TimeRange | null;
}

const WORD_NUMBERS: Record<string, number> = {
  one: 1, two: 2, three: 3, four: 4, five: 5,
  six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  eleven: 11, twelve: 12, twenty: 20, thirty: 30,
};

const SHORTHAND_RE =
  /\b(?:last|past)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty)?\s*(hours?|hrs?|h|minutes?|mins?|m|days?|d|weeks?|wks?|w)\b/i;

const MAX_RANGE_SECONDS = 7 * 86400;

export function parseTimeFilter(input: string): ParseResult {
  const now = Math.floor(Date.now() / 1000);

  const shorthand = input.match(SHORTHAND_RE);
  if (shorthand) {
    const rawN = shorthand[1];
    const n = rawN
      ? (WORD_NUMBERS[rawN.toLowerCase()] ?? parseInt(rawN)) || 1
      : 1;
    const unit = shorthand[2]![0]!.toLowerCase();
    const mult: Record<string, number> = {
      h: 3600, m: 60, d: 86400, w: 604800,
    };
    return {
      cleanQuery: strip(input, shorthand[0]),
      timeRange: clamp({ start: now - n * (mult[unit] ?? 3600), end: now }),
    };
  }

  const morningMatch = input.match(/\bthis\s+morning\b/i);
  if (morningMatch) {
    const sixAm = new Date();
    sixAm.setHours(6, 0, 0, 0);
    return {
      cleanQuery: strip(input, morningMatch[0]),
      timeRange: { start: Math.floor(sixAm.getTime() / 1000), end: now },
    };
  }

  const tonightMatch = input.match(/\b(?:tonight|this\s+evening)\b/i);
  if (tonightMatch) {
    const sixPm = new Date();
    sixPm.setHours(18, 0, 0, 0);
    return {
      cleanQuery: strip(input, tonightMatch[0]),
      timeRange: { start: Math.floor(sixPm.getTime() / 1000), end: now },
    };
  }

  const parsed = chrono.parse(input, new Date(), { forwardDate: false });
  if (parsed.length > 0) {
    const result = parsed[0]!;
    const startDate = result.start.date();
    const noTime = !result.start.isCertain("hour") && !result.start.isCertain("minute");
    let endDate: Date;

    if (noTime) {
      startDate.setHours(0, 0, 0, 0);
    }

    if (result.end) {
      endDate = result.end.date();
    } else if (noTime) {
      endDate = new Date(startDate);
      endDate.setHours(23, 59, 59, 999);
      if (endDate.getTime() > Date.now()) {
        endDate = new Date();
      }
    } else {
      endDate = new Date(Math.min(startDate.getTime() + 3600_000, Date.now()));
    }

    return {
      cleanQuery: strip(input, result.text),
      timeRange: clamp({
        start: Math.floor(startDate.getTime() / 1000),
        end: Math.floor(endDate.getTime() / 1000),
      }),
    };
  }

  return { cleanQuery: input, timeRange: null };
}

function clamp(range: TimeRange): TimeRange {
  if (range.end - range.start > MAX_RANGE_SECONDS) {
    return { start: range.end - MAX_RANGE_SECONDS, end: range.end };
  }
  return range;
}

function strip(input: string, match: string): string {
  return input.replace(match, "").replace(/\s+/g, " ").trim();
}
