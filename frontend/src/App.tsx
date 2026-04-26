import { useCallback, useEffect, useRef, useState } from "react";
import AboutModal from "./components/AboutModal";
import EventPanel from "./components/EventPanel";
import Map from "./components/Map";
import SearchBox from "./components/SearchBox";
import TranscriptList from "./components/TranscriptList";
import TranscriptPanel from "./components/TranscriptPanel";
import { fetchEvents, searchTranscripts } from "./lib/api";
import type { ScannerEvent, TimeRange, TranscriptResult } from "./lib/types";

const POLL_INTERVAL = 15_000;

function freshDefault(): TimeRange {
  const now = Math.floor(Date.now() / 1000);
  return { start: now - 21600, end: now };
}

export default function App() {
  const [timeRange, setTimeRange] = useState<TimeRange>(freshDefault);
  const [events, setEvents] = useState<ScannerEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<ScannerEvent | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [aboutOpen, setAboutOpen] = useState(false);
  const [rawInput, setRawInput] = useState("");
  const [transcriptResults, setTranscriptResults] = useState<TranscriptResult[]>([]);
  const [selectedTranscript, setSelectedTranscript] = useState<TranscriptResult | null>(null);
  const loadEvents = useCallback(async () => {
    const data = await fetchEvents(
      timeRange.start,
      timeRange.end,
      undefined,
      searchQuery || undefined,
    );
    setEvents(data);
  }, [timeRange, searchQuery]);

  const loadTranscripts = useCallback(async () => {
    if (!rawInput.trim()) {
      setTranscriptResults([]);
      return;
    }
    const data = await searchTranscripts(searchQuery, timeRange.start, timeRange.end);
    setTranscriptResults(data);
  }, [searchQuery, timeRange, rawInput]);

  useEffect(() => { loadEvents(); }, [loadEvents]);
  useEffect(() => { loadTranscripts(); }, [loadTranscripts]);

  const timeRangeRef = useRef(timeRange);
  timeRangeRef.current = timeRange;
  const loadEventsRef = useRef(loadEvents);
  loadEventsRef.current = loadEvents;
  const loadTranscriptsRef = useRef(loadTranscripts);
  loadTranscriptsRef.current = loadTranscripts;
  const rawInputRef = useRef(rawInput);
  rawInputRef.current = rawInput;

  useEffect(() => {
    const id = setInterval(() => {
      const r = timeRangeRef.current;
      const now = Math.floor(Date.now() / 1000);
      const duration = r.end - r.start;
      setTimeRange({ start: now - duration, end: now });
      loadEventsRef.current();
      if (rawInputRef.current.trim()) loadTranscriptsRef.current();
    }, POLL_INTERVAL);
    return () => clearInterval(id);
  }, []);

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
