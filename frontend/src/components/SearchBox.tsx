import { useCallback, useEffect, useRef, useState } from "react";
import { parseTimeFilter } from "../lib/parseTimeFilter";
import type { TimeRange } from "../lib/types";

interface Props {
  onTimeRangeChange: (range: TimeRange | null) => void;
  onSearch: (query: string) => void;
  onInputChange?: (raw: string) => void;
  onAbout: () => void;
}

const PLACEHOLDERS = [
  "Search dispatch audio...",
  "robbery last 2 hours",
  "shots fired tonight",
  "242 this morning",
  "Venice Blvd yesterday",
  "pursuit last 30 minutes",
  "DUI last 3 days",
];

const ROTATE_MS = 4000;
const FADE_MS = 300;

function formatTimeLabel(range: TimeRange): string {
  const fmt = (ts: number) => {
    const d = new Date(ts * 1000);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) {
      return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    }
    return d.toLocaleDateString(undefined, {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });
  };
  return `${fmt(range.start)} – ${fmt(range.end)}`;
}

export default function SearchBox({
  onTimeRangeChange,
  onSearch,
  onInputChange,
  onAbout,
}: Props) {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const [activeRange, setActiveRange] = useState<TimeRange | null>(null);
  const [rangeTooLarge, setRangeTooLarge] = useState(false);
  const [phIdx, setPhIdx] = useState(0);
  const [phVisible, setPhVisible] = useState(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const callbacksRef = useRef({ onTimeRangeChange, onSearch });
  callbacksRef.current = { onTimeRangeChange, onSearch };

  useEffect(() => {
    if (query || focused) return;
    const id = setInterval(() => {
      setPhVisible(false);
      setTimeout(() => {
        setPhIdx((i) => (i + 1) % PLACEHOLDERS.length);
        setPhVisible(true);
      }, FADE_MS);
    }, ROTATE_MS);
    return () => clearInterval(id);
  }, [query, focused]);

  useEffect(() => {
    if (!query) return;
    const { timeRange: parsed, tooLarge } = parseTimeFilter(query);
    if (!parsed || tooLarge) return;
    const id = setInterval(() => {
      const { cleanQuery, timeRange: fresh, tooLarge: freshTooLarge } = parseTimeFilter(query);
      if (fresh && !freshTooLarge) {
        callbacksRef.current.onTimeRangeChange(fresh);
        setActiveRange(fresh);
        callbacksRef.current.onSearch(cleanQuery.trim());
      }
    }, 10_000);
    return () => clearInterval(id);
  }, [query]);

  const handleChange = useCallback((value: string) => {
    setQuery(value);
    onInputChange?.(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const { cleanQuery, timeRange: parsed, tooLarge } = parseTimeFilter(value);
    if (tooLarge) {
      setRangeTooLarge(true);
      setActiveRange(null);
      onTimeRangeChange(null);
      onSearch("");
      return;
    }
    setRangeTooLarge(false);
    if (parsed) {
      onTimeRangeChange(parsed);
      setActiveRange(parsed);
    } else {
      setActiveRange(null);
    }

    debounceRef.current = setTimeout(() => onSearch(cleanQuery.trim()), 300);
  }, [onInputChange, onTimeRangeChange, onSearch]);

  const handleClear = () => {
    setQuery("");
    setActiveRange(null);
    setRangeTooLarge(false);
    onInputChange?.("");
    onSearch("");
    const now = Math.floor(Date.now() / 1000);
    onTimeRangeChange({ start: now - 21600, end: now });
  };

  return (
    <div
      className="panel rounded-lg shadow-md transition-colors duration-150"
      style={focused ? { borderColor: "#3d444d" } : undefined}
    >
      <div className="flex items-baseline justify-between px-3 pt-2 pb-0">
        <span className="text-[13px] font-bold tracking-tight text-[#e6edf3] select-none">
          blotter
        </span>
        <button
          onClick={onAbout}
          className="text-[11px] text-[#545d68] hover:text-[#adbac7] transition-colors cursor-pointer"
        >
          About
        </button>
      </div>

      <div className="relative flex items-center">
        <div className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none">
          <svg
            className="w-3.5 h-3.5"
            fill="none"
            stroke={focused ? "#8b949e" : "#545d68"}
            viewBox="0 0 24 24"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
            />
          </svg>
        </div>

        {!query && !focused && (
          <span
            className="absolute left-9 top-1/2 -translate-y-1/2 text-[16px] sm:text-sm text-[#545d68] pointer-events-none select-none transition-opacity duration-300"
            style={{ opacity: phVisible ? 1 : 0 }}
          >
            {PLACEHOLDERS[phIdx]}
          </span>
        )}

        <input
          type="text"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={focused ? "Search dispatch audio..." : ""}
          className="
            w-full pl-9 pr-9 py-2.5
            text-[16px] sm:text-sm text-[#e6edf3] placeholder-[#545d68]
            bg-transparent
            rounded-lg border-0
            focus:outline-none
          "
        />

        <div className="absolute right-3 top-1/2 -translate-y-1/2">
          {query ? (
            <button
              onClick={handleClear}
              className="w-5 h-5 flex items-center justify-center rounded text-[#545d68] hover:text-[#adbac7] transition-colors"
            >
              <svg
                className="w-3 h-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                strokeWidth={2.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          ) : null}
        </div>
      </div>

      {rangeTooLarge && (
        <div className="px-3 pb-2 -mt-0.5">
          <span className="inline-flex items-center gap-1.5 text-[11px] text-[#e5534b]">
            <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
            Time range too large, max 7 days
          </span>
        </div>
      )}

      {activeRange && !rangeTooLarge && (
        <div className="px-3 pb-2 -mt-0.5 flex items-center justify-between">
          <span className="inline-flex items-center gap-1.5 text-[11px] text-[#539bf5]">
            <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2m6-2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {formatTimeLabel(activeRange)}
          </span>
          <a
            href="https://www.buymeacoffee.com/seanreid"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] text-[#3d444d] hover:text-[#545d68] transition-colors"
          >
            Support
          </a>
        </div>
      )}
    </div>
  );
}
