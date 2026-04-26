import { useCallback, useEffect, useState } from "react";
import EventPanel from "./components/EventPanel";
import Map from "./components/Map";
import SearchBox from "./components/SearchBox";
import TimeSlider from "./components/TimeSlider";
import { fetchEvents } from "./lib/api";
import type {
  ScannerEvent,
  TimeRange,
  TranscriptResult,
} from "./lib/types";

const now = Math.floor(Date.now() / 1000);
const DEFAULT_RANGE: TimeRange = { start: now - 86400, end: now };

export default function App() {
  const [timeRange, setTimeRange] = useState<TimeRange>(DEFAULT_RANGE);
  const [events, setEvents] = useState<ScannerEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<ScannerEvent | null>(null);
  const [selectedTranscript, setSelectedTranscript] =
    useState<TranscriptResult | null>(null);
  const [searchResults, setSearchResults] = useState<TranscriptResult[]>([]);
  const [bounds, setBounds] = useState<{
    west: number;
    south: number;
    east: number;
    north: number;
  } | null>(null);

  useEffect(() => {
    const load = async () => {
      const data = await fetchEvents(
        timeRange.start,
        timeRange.end,
        bounds ?? undefined,
      );
      setEvents(data);
    };
    load();
  }, [timeRange, bounds]);

  const handleSearchResults = useCallback(
    (results: TranscriptResult[]) => {
      setSearchResults(results);
      setSelectedTranscript(results[0] ?? null);
    },
    [],
  );

  const handleEventClick = useCallback((event: ScannerEvent) => {
    setSelectedEvent(event);
    setSelectedTranscript(null);
  }, []);

  const handleClosePanel = useCallback(() => {
    setSelectedEvent(null);
    setSelectedTranscript(null);
  }, []);

  const handleSelectTranscript = useCallback((r: TranscriptResult) => {
    setSelectedTranscript(r);
    setSelectedEvent(null);
    setSearchResults([]);
  }, []);

  const hasPanel = !!(selectedEvent || selectedTranscript);

  return (
    <div className="h-full w-full relative flex flex-col bg-slate-950">
      <div className="flex-1 relative">
        <Map
          events={events}
          onBoundsChange={setBounds}
          onEventClick={handleEventClick}
        />

        <div className="absolute top-0 left-0 right-0 z-10 pointer-events-none">
          <div className="pointer-events-auto w-full max-w-md">
            <SearchBox
              timeRange={timeRange}
              onResults={handleSearchResults}
            />
          </div>
        </div>

        {searchResults.length > 0 && (
          <div className="absolute top-[68px] left-3 z-20 glass-panel rounded-xl shadow-xl max-w-md w-[calc(100%-1.5rem)] sm:w-auto sm:min-w-[360px] max-h-72 overflow-y-auto">
            {searchResults.map((r, i) => (
              <button
                key={`${r.archive_ts}-${i}`}
                onClick={() => handleSelectTranscript(r)}
                className="block w-full text-left px-4 py-3 transition-colors duration-150 hover:bg-white/[0.06] border-b border-slate-700/30 last:border-0 group"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium text-sm text-slate-100 truncate group-hover:text-indigo-300 transition-colors">
                    {r.feed_name}
                  </span>
                  <span className="text-[11px] text-slate-500 shrink-0 tabular-nums">
                    {new Date(r.archive_ts).toLocaleString(undefined, {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                  {r.transcript.slice(0, 140)}
                </p>
              </button>
            ))}
          </div>
        )}

        <EventPanel
          event={selectedEvent}
          transcript={selectedTranscript}
          onClose={handleClosePanel}
        />
      </div>

      <div className={`shrink-0 transition-all duration-300 ${hasPanel ? "md:mr-[400px]" : ""}`}>
        <TimeSlider range={timeRange} onChange={setTimeRange} />
      </div>
    </div>
  );
}
