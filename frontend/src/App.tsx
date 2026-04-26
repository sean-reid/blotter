import { useCallback, useEffect, useState } from "react";
import AboutModal from "./components/AboutModal";
import EventPanel from "./components/EventPanel";
import Map from "./components/Map";
import SearchBox from "./components/SearchBox";
import TranscriptList from "./components/TranscriptList";
import TranscriptPanel from "./components/TranscriptPanel";
import { fetchEvents, searchTranscripts } from "./lib/api";
import type { ScannerEvent, TimeRange, TranscriptResult } from "./lib/types";

const now = Math.floor(Date.now() / 1000);
const DEFAULT_RANGE: TimeRange = { start: now - 86400, end: now };

export default function App() {
  const [timeRange, setTimeRange] = useState<TimeRange>(DEFAULT_RANGE);
  const [events, setEvents] = useState<ScannerEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<ScannerEvent | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [aboutOpen, setAboutOpen] = useState(false);
  const [rawInput, setRawInput] = useState("");
  const [transcriptResults, setTranscriptResults] = useState<TranscriptResult[]>([]);
  const [selectedTranscript, setSelectedTranscript] = useState<TranscriptResult | null>(null);
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
        searchQuery || undefined,
      );
      setEvents(data);
    };
    load();
  }, [timeRange, bounds, searchQuery]);

  useEffect(() => {
    if (!rawInput.trim()) {
      setTranscriptResults([]);
      return;
    }
    const load = async () => {
      const data = await searchTranscripts(searchQuery, timeRange.start, timeRange.end);
      setTranscriptResults(data);
    };
    load();
  }, [searchQuery, timeRange, rawInput]);

  const handleEventClick = useCallback((event: ScannerEvent) => {
    setSelectedEvent(event);
    setSelectedTranscript(null);
  }, []);

  const handleTranscriptSelect = useCallback((result: TranscriptResult) => {
    setSelectedTranscript(result);
    setSelectedEvent(null);
  }, []);

  const handleClosePanel = useCallback(() => {
    setSelectedEvent(null);
    setSelectedTranscript(null);
  }, []);

  return (
    <div className="h-full w-full relative" style={{ background: "#0d1117" }}>
      <Map
        events={events}
        onBoundsChange={setBounds}
        onEventClick={handleEventClick}
      />

      <div className="absolute top-0 left-0 right-0 z-10 pointer-events-none">
        <div className="pointer-events-auto w-full max-w-md p-3">
          <SearchBox
            onTimeRangeChange={setTimeRange}
            onSearch={setSearchQuery}
            onInputChange={setRawInput}
            onAbout={() => setAboutOpen(true)}
          />
          {rawInput.trim() && transcriptResults.length > 0 && (
            <TranscriptList
              results={transcriptResults}
              query={searchQuery}
              onSelect={handleTranscriptSelect}
            />
          )}
        </div>
      </div>

      <EventPanel
        event={selectedEvent}
        onClose={handleClosePanel}
      />

      {selectedTranscript && (
        <TranscriptPanel
          transcript={selectedTranscript}
          onClose={handleClosePanel}
        />
      )}

      <AboutModal open={aboutOpen} onClose={() => setAboutOpen(false)} />
    </div>
  );
}
