import { useCallback, useRef, useState } from "react";
import { searchTranscripts } from "../lib/api";
import type { TimeRange, TranscriptResult } from "../lib/types";

interface Props {
  timeRange: TimeRange;
  onResults: (results: TranscriptResult[]) => void;
}

export default function SearchBox({ timeRange, onResults }: Props) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const doSearch = useCallback(
    async (term: string) => {
      if (!term.trim()) {
        onResults([]);
        return;
      }
      setLoading(true);
      try {
        const results = await searchTranscripts(
          term.trim(),
          timeRange.start,
          timeRange.end,
        );
        onResults(results);
      } finally {
        setLoading(false);
      }
    },
    [timeRange, onResults],
  );

  const handleChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(value), 300);
  };

  const handleClear = () => {
    setQuery("");
    onResults([]);
  };

  return (
    <div className="glass-panel rounded-xl shadow-xl m-3">
      <div className="relative flex items-center">
        <div className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none">
          <svg
            className="w-4 h-4 text-slate-400"
            fill="none"
            stroke="currentColor"
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

        <input
          type="text"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          placeholder="Search dispatch audio"
          className="
            w-full pl-10 pr-10 py-3
            text-sm text-slate-100 placeholder-slate-500
            bg-transparent
            rounded-xl
            border-0
            focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:ring-offset-0
            transition-shadow duration-200
          "
        />

        <div className="absolute right-3 top-1/2 -translate-y-1/2">
          {loading ? (
            <div className="w-4 h-4 border-2 border-slate-600 border-t-indigo-400 rounded-full animate-spin" />
          ) : query ? (
            <button
              onClick={handleClear}
              className="w-6 h-6 flex items-center justify-center rounded-full text-slate-500 hover:text-slate-300 hover:bg-slate-700/50 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
