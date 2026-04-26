import { useRef, useState } from "react";
import { parseTimeFilter } from "../lib/parseTimeFilter";
import type { TimeRange } from "../lib/types";

interface Props {
  onTimeRangeChange: (range: TimeRange) => void;
  onSearch: (query: string) => void;
  onInputChange?: (raw: string) => void;
  onAbout: () => void;
}

export default function SearchBox({
  onTimeRangeChange,
  onSearch,
  onInputChange,
  onAbout,
}: Props) {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const handleChange = (value: string) => {
    setQuery(value);
    onInputChange?.(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const { cleanQuery, timeRange: parsed } = parseTimeFilter(value);
    if (parsed) onTimeRangeChange(parsed);

    debounceRef.current = setTimeout(() => onSearch(cleanQuery.trim()), 300);
  };

  const handleClear = () => {
    setQuery("");
    onInputChange?.("");
    onSearch("");
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

        <input
          type="text"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="Search dispatch audio..."
          className="
            w-full pl-9 pr-9 py-2.5
            text-sm text-[#e6edf3] placeholder-[#545d68]
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
    </div>
  );
}
