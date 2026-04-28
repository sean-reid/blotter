import * as chrono from "chrono-node";
import type { TimeRange } from "./types";

export interface ParseResult {
  cleanQuery: string;
  timeRange: TimeRange | null;
  tooLarge: boolean;
}

const WORD_NUMBERS: Record<string, number> = {
  one: 1, two: 2, three: 3, four: 4, five: 5,
  six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  eleven: 11, twelve: 12, twenty: 20, thirty: 30,
};

const SHORTHAND_RE =
  /\b(?:last|past)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty)?\s*(hours?|hrs?|h|minutes?|mins?|m|days?|d|weeks?|wks?|w)\b/i;

export const MAX_RANGE_SECONDS = 7 * 86400;

function check(range: TimeRange, cleanQuery: string): ParseResult {
  if (range.end - range.start > MAX_RANGE_SECONDS) {
    return { cleanQuery, timeRange: null, tooLarge: true };
  }
  return { cleanQuery, timeRange: range, tooLarge: false };
}

const TOO_LARGE_RE =
  /\b(?:last|past)\s+(?:\d+\s+)?(?:months?|years?)\b/i;

export function parseTimeFilter(input: string): ParseResult {
  const now = Math.floor(Date.now() / 1000);

  if (TOO_LARGE_RE.test(input)) {
    return { cleanQuery: input, timeRange: null, tooLarge: true };
  }

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
    return check(
      { start: now - n * (mult[unit] ?? 3600), end: now },
      strip(input, shorthand[0]),
    );
  }

  const thisWeekMatch = input.match(/\bthis\s+week\b/i);
  if (thisWeekMatch) {
    const d = new Date();
    const day = d.getDay();
    const diff = day === 0 ? 6 : day - 1;
    const monday = new Date(d);
    monday.setDate(d.getDate() - diff);
    monday.setHours(0, 0, 0, 0);
    return check(
      { start: Math.floor(monday.getTime() / 1000), end: now },
      strip(input, thisWeekMatch[0]),
    );
  }

  const thisMonthMatch = input.match(/\bthis\s+month\b/i);
  if (thisMonthMatch) {
    const first = new Date();
    first.setDate(1);
    first.setHours(0, 0, 0, 0);
    return check(
      { start: Math.floor(first.getTime() / 1000), end: now },
      strip(input, thisMonthMatch[0]),
    );
  }

  const morningMatch = input.match(/\bthis\s+morning\b/i);
  if (morningMatch) {
    const sixAm = new Date();
    sixAm.setHours(6, 0, 0, 0);
    return check(
      { start: Math.floor(sixAm.getTime() / 1000), end: now },
      strip(input, morningMatch[0]),
    );
  }

  const tonightMatch = input.match(/\b(?:tonight|this\s+evening)\b/i);
  if (tonightMatch) {
    const sixPm = new Date();
    sixPm.setHours(18, 0, 0, 0);
    return check(
      { start: Math.floor(sixPm.getTime() / 1000), end: now },
      strip(input, tonightMatch[0]),
    );
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

    return check(
      {
        start: Math.floor(startDate.getTime() / 1000),
        end: Math.floor(endDate.getTime() / 1000),
      },
      strip(input, result.text),
    );
  }

  return { cleanQuery: input, timeRange: null, tooLarge: false };
}

function strip(input: string, match: string): string {
  return input.replace(match, "").replace(/\s+/g, " ").trim();
}
