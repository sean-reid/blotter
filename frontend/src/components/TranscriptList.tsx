import type { TranscriptResult } from "../lib/types";
import Tags from "./Tags";

interface Props {
  results: TranscriptResult[];
  query: string;
  onSelect: (result: TranscriptResult) => void;
}

function formatDate(ts: string): string {
  const utc = ts.includes("Z") || ts.includes("+") ? ts : ts.replace(" ", "T") + "Z";
  return new Date(utc).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function snippet(text: string, query: string, maxLen = 120): string {
  const lower = text.toLowerCase();
  const idx = lower.indexOf(query.toLowerCase());
  if (idx === -1) return text.slice(0, maxLen);
  const start = Math.max(0, idx - 40);
  const end = Math.min(text.length, idx + query.length + 80);
  let s = text.slice(start, end);
  if (start > 0) s = "..." + s;
  if (end < text.length) s = s + "...";
  return s;
}

export default function TranscriptList({ results, query, onSelect }: Props) {
  if (!results.length) return null;

  return (
    <div
      className="panel rounded-lg shadow-md mt-1 overflow-hidden"
      style={{ maxHeight: "50vh" }}
    >
      <div className="px-3 py-2 border-b border-[#2d333b]">
        <span className="text-[11px] font-medium uppercase tracking-wider text-[#545d68]">
          Transcripts ({results.length})
        </span>
      </div>
      <div className="overflow-y-auto" style={{ maxHeight: "calc(50vh - 32px)" }}>
        {results.map((r, i) => (
          <button
            key={`${r.feed_id}-${r.archive_ts}-${i}`}
            onClick={() => onSelect(r)}
            className="
              w-full text-left px-3 py-2.5
              border-b border-[#2d333b]/50 last:border-0
              hover:bg-[#1c2128] transition-colors
              cursor-pointer
            "
          >
            <div className="flex items-baseline justify-between gap-2 mb-1">
              <span className="text-[12px] font-medium text-[#adbac7] truncate">
                {r.feed_name || r.feed_id}
              </span>
              <span className="text-[10px] tabular-nums text-[#545d68] shrink-0">
                {formatDate(r.archive_ts)}
              </span>
            </div>
            <div className="text-[12px] leading-relaxed text-[#545d68] line-clamp-2">
              {snippet(r.transcript, query)}
            </div>
            {r.tags && <div className="mt-1"><Tags tags={r.tags} /></div>}
          </button>
        ))}
      </div>
    </div>
  );
}
