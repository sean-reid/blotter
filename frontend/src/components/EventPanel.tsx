import { useCallback, useEffect, useRef, useState } from "react";
import type { ScannerEvent, TranscriptResult, TranscriptSegment } from "../lib/types";
import { fetchSurroundingTranscripts } from "../lib/api";
import Tags from "./Tags";
import TranscriptPlayer from "./TranscriptPlayer";

interface Props {
  event: ScannerEvent | null;
  onClose: () => void;
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

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-medium uppercase tracking-wider text-[#545d68] mb-1">
      {children}
    </div>
  );
}

function parseSegments(raw: string): TranscriptSegment[] {
  if (!raw) return [];
  try {
    return JSON.parse(raw) as TranscriptSegment[];
  } catch {
    return [];
  }
}

function formatTime(ts: string): string {
  const utc = ts.includes("Z") || ts.includes("+") ? ts : ts.replace(" ", "T") + "Z";
  return new Date(utc).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function EventPanel({ event, onClose }: Props) {
  const [visible, setVisible] = useState(false);
  const [transcripts, setTranscripts] = useState<TranscriptResult[]>([]);
  const [loadingTranscript, setLoadingTranscript] = useState(false);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [dragY, setDragY] = useState(0);
  const dragStartY = useRef(0);
  const dragging = useRef(false);

  useEffect(() => {
    if (event) {
      requestAnimationFrame(() => { setVisible(true); });
      setLoadingTranscript(true);
      setTranscripts([]);
      setExpandedIdx(null);
      setDragY(0);
      fetchSurroundingTranscripts(event.feed_id, event.archive_ts)
        .then((results) => {
          setTranscripts(results);
          if (results.length > 0) {
            let closest = 0;
            let minDiff = Infinity;
            const eventTs = new Date(event.archive_ts.includes("Z") || event.archive_ts.includes("+") ? event.archive_ts : event.archive_ts.replace(" ", "T") + "Z").getTime();
            for (let i = 0; i < results.length; i++) {
              const ts = results[i]!.archive_ts;
              const t = new Date(ts.includes("Z") || ts.includes("+") ? ts : ts.replace(" ", "T") + "Z").getTime();
              const diff = Math.abs(t - eventTs);
              if (diff < minDiff) { minDiff = diff; closest = i; }
            }
            setExpandedIdx(closest);
          }
        })
        .catch(() => setTranscripts([]))
        .finally(() => setLoadingTranscript(false));
    } else {
      setVisible(false);
      setTranscripts([]);
      setExpandedIdx(null);
    }
  }, [event]);

  useEffect(() => {
    if (!event) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [event, onClose]);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    dragStartY.current = e.touches[0]!.clientY;
    dragging.current = true;
  }, []);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    if (!dragging.current) return;
    const dy = e.touches[0]!.clientY - dragStartY.current;
    setDragY(Math.max(0, dy));
  }, []);

  const onTouchEnd = useCallback(() => {
    dragging.current = false;
    if (dragY > 60) {
      onClose();
    }
    setDragY(0);
  }, [dragY, onClose]);

  if (!event) return null;

  return (
    <>
      <div
        className={`
          fixed inset-0 z-40 bg-black/40 md:hidden
          transition-opacity duration-300
          ${visible ? "opacity-100" : "opacity-0 pointer-events-none"}
        `}
        onClick={onClose}
      />

      <div
        className={`
          fixed z-50
          bottom-0 left-0 right-0
          md:top-0 md:right-0 md:left-auto md:bottom-0 md:w-[380px]

          panel
          rounded-t-xl md:rounded-none md:border-l md:border-t-0

          max-h-[70vh] md:max-h-full
          overflow-hidden
          flex flex-col

          ${dragging.current ? "" : "transition-transform duration-300"}
          ${visible
            ? "translate-y-0 md:translate-x-0"
            : "translate-y-full md:translate-y-0 md:translate-x-full"
          }
        `}
        style={{
          transitionTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)",
          ...(dragY > 0 ? { transform: `translateY(${dragY}px)` } : {}),
        }}
      >
        <div
          className="md:hidden flex justify-center pt-2 pb-3 cursor-grab active:cursor-grabbing"
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
        >
          <div className="w-10 h-1 rounded-full bg-[#3d444d]" />
        </div>

        <div
          className="shrink-0 border-b border-[#2d333b] px-4 py-3 flex justify-between items-center"
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
        >
          <h3 className="font-medium text-sm text-[#e6edf3]">Event</h3>
          <button
            onClick={onClose}
            className="
              w-7 h-7 min-w-[44px] min-h-[44px]
              flex items-center justify-center
              rounded
              text-[#545d68] hover:text-[#adbac7]
              transition-colors duration-100
            "
            aria-label="Close panel"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <div>
            <FieldLabel>Location</FieldLabel>
            <div className="text-sm font-medium text-[#e6edf3] leading-snug">
              {event.normalized}
            </div>
            <div className="text-[11px] text-[#545d68] tabular-nums font-mono mt-1">
              {event.latitude.toFixed(5)}, {event.longitude.toFixed(5)}
            </div>
          </div>

          <div>
            <FieldLabel>Time</FieldLabel>
            <div className="text-sm text-[#adbac7] tabular-nums">
              {formatDate(event.event_ts)}
            </div>
          </div>

          <div>
            <FieldLabel>Feed</FieldLabel>
            <div className="text-sm text-[#adbac7]">
              {transcripts[0]?.feed_name || event.feed_id}
            </div>
          </div>

          {event.tags && (
            <div>
              <FieldLabel>Codes</FieldLabel>
              <Tags tags={event.tags} />
            </div>
          )}

          <div>
            <FieldLabel>Dispatch ({transcripts.length})</FieldLabel>
            {loadingTranscript ? (
              <div className="text-xs text-[#545d68] italic">Loading...</div>
            ) : transcripts.length > 0 ? (
              <div className="space-y-2">
                {transcripts.map((t, i) => {
                  const isExpanded = expandedIdx === i;
                  return (
                    <div key={`${t.feed_id}-${t.archive_ts}`} className="rounded border border-[#2d333b] overflow-hidden">
                      <button
                        onClick={() => setExpandedIdx(isExpanded ? null : i)}
                        className={`
                          w-full text-left px-3 py-2 flex items-center justify-between gap-2
                          transition-colors duration-100
                          ${isExpanded ? "bg-[#539bf5]/10" : "hover:bg-[#1c2128]"}
                        `}
                      >
                        <span className="text-[12px] tabular-nums text-[#adbac7]">
                          {formatTime(t.archive_ts)}
                        </span>
                        <span className="text-[12px] text-[#545d68] truncate flex-1 text-right">
                          {t.transcript.slice(0, 60)}{t.transcript.length > 60 ? "..." : ""}
                        </span>
                        <svg
                          className={`w-3 h-3 shrink-0 text-[#545d68] transition-transform duration-150 ${isExpanded ? "rotate-180" : ""}`}
                          fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>
                      {isExpanded && (
                        <div className="px-3 pb-3 pt-1">
                          <TranscriptPlayer
                            audioUrl={t.audio_url}
                            segments={parseSegments(t.segments)}
                            durationMs={t.duration_ms}
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-xs text-[#545d68] italic">No transcripts available</div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
