import type { ScannerEvent, TranscriptResult } from "../lib/types";
import Tags from "./Tags";

interface Props {
  results: TranscriptResult[];
  query: string;
  matchedEvents: ScannerEvent[];
  selectedTranscript: TranscriptResult | null;
  selectedEvent: ScannerEvent | null;
  onSelectTranscript: (result: TranscriptResult) => void;
  onSelectEvent: (event: ScannerEvent) => void;
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

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 py-2 border-b border-[#2d333b]">
      <span className="text-[11px] font-medium uppercase tracking-wider text-[#545d68]">
        {children}
      </span>
    </div>
  );
}

export default function TranscriptList({
  results, query, matchedEvents, selectedTranscript, selectedEvent,
  onSelectTranscript, onSelectEvent,
}: Props) {
  if (!results.length && !matchedEvents.length) return null;

  return (
    <div
      className="panel rounded-lg shadow-md mt-1 overflow-hidden"
      style={{ maxHeight: "50vh" }}
    >
      <div className="overflow-y-auto" style={{ maxHeight: "50vh" }}>
        {matchedEvents.length > 0 && (
          <>
            <SectionHeader>Events ({matchedEvents.length})</SectionHeader>
            {matchedEvents.slice(0, 50).map((e) => {
              const isSelected = selectedEvent
                && e.feed_id === selectedEvent.feed_id
                && e.event_ts === selectedEvent.event_ts;
              return (
                <button
                  key={`evt-${e.feed_id}-${e.event_ts}`}
                  onClick={() => onSelectEvent(e)}
                  className={`
                    w-full text-left px-3 py-2.5
                    border-b border-[#2d333b]/50
                    transition-colors cursor-pointer
                    ${isSelected ? "bg-[#539bf5]/10 border-l-2 border-l-[#539bf5]" : "hover:bg-[#1c2128]"}
                  `}
                >
                  <div className="flex items-baseline justify-between gap-2 mb-1">
                    <span className="text-[12px] font-medium text-[#adbac7] truncate flex items-center gap-1.5">
                      <svg className="w-3 h-3 shrink-0 text-[#e5534b]" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5a2.5 2.5 0 010-5 2.5 2.5 0 010 5z" />
                      </svg>
                      {e.normalized}
                    </span>
                    <span className="text-[10px] tabular-nums text-[#545d68] shrink-0">
                      {formatDate(e.event_ts)}
                    </span>
                  </div>
                  {(e.summary || e.context) && (
                    <div className="text-[12px] leading-relaxed text-[#545d68] line-clamp-2">
                      {e.summary || snippet(e.context, query)}
                    </div>
                  )}
                  {e.tags && <div className="mt-1"><Tags tags={e.tags} /></div>}
                </button>
              );
            })}
          </>
        )}

        {results.length > 0 && (
          <>
            <SectionHeader>Transcripts ({results.length})</SectionHeader>
            {results.map((r, i) => {
              const isSelected = selectedTranscript
                && r.feed_id === selectedTranscript.feed_id
                && r.archive_ts === selectedTranscript.archive_ts;
              return (
                <button
                  key={`tr-${r.feed_id}-${r.archive_ts}-${i}`}
                  onClick={() => onSelectTranscript(r)}
                  className={`
                    w-full text-left px-3 py-2.5
                    border-b border-[#2d333b]/50 last:border-0
                    transition-colors cursor-pointer
                    ${isSelected ? "bg-[#539bf5]/10 border-l-2 border-l-[#539bf5]" : "hover:bg-[#1c2128]"}
                  `}
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
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
