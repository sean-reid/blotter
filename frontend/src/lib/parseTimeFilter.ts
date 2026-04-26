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

export function parseTimeFilter(input: string): ParseResult {
  const now = Math.floor(Date.now() / 1000);

  const relativeMatch = input.match(
    /\b(?:last|past)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty)?\s*(hours?|hrs?|h|minutes?|mins?|m|days?|d|weeks?|wks?|w)\b/i,
  );
  if (relativeMatch) {
    const rawN = relativeMatch[1];
    const n = rawN
      ? (WORD_NUMBERS[rawN.toLowerCase()] ?? parseInt(rawN)) || 1
      : 1;
    const unit = relativeMatch[2]![0]!.toLowerCase();
    const mult: Record<string, number> = {
      h: 3600,
      m: 60,
      d: 86400,
      w: 604800,
    };
    return {
      cleanQuery: strip(input, relativeMatch[0]),
      timeRange: { start: now - n * (mult[unit] ?? 3600), end: now },
    };
  }

  const todayMatch = input.match(/\btoday\b/i);
  if (todayMatch) {
    const sod = new Date();
    sod.setHours(0, 0, 0, 0);
    return {
      cleanQuery: strip(input, todayMatch[0]),
      timeRange: { start: Math.floor(sod.getTime() / 1000), end: now },
    };
  }

  const yesterdayMatch = input.match(/\byesterday\b/i);
  if (yesterdayMatch) {
    const start = new Date();
    start.setDate(start.getDate() - 1);
    start.setHours(0, 0, 0, 0);
    const end = new Date();
    end.setHours(0, 0, 0, 0);
    return {
      cleanQuery: strip(input, yesterdayMatch[0]),
      timeRange: {
        start: Math.floor(start.getTime() / 1000),
        end: Math.floor(end.getTime() / 1000),
      },
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

  const eveningMatch = input.match(/\b(?:tonight|this\s+evening)\b/i);
  if (eveningMatch) {
    const sixPm = new Date();
    sixPm.setHours(18, 0, 0, 0);
    return {
      cleanQuery: strip(input, eveningMatch[0]),
      timeRange: { start: Math.floor(sixPm.getTime() / 1000), end: now },
    };
  }

  const weekMatch = input.match(/\bthis\s+week\b/i);
  if (weekMatch) {
    return {
      cleanQuery: strip(input, weekMatch[0]),
      timeRange: { start: now - 604800, end: now },
    };
  }

  return { cleanQuery: input, timeRange: null };
}

function strip(input: string, match: string): string {
  return input.replace(match, "").replace(/\s+/g, " ").trim();
}
