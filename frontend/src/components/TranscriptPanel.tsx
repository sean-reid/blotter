import { useCallback, useRef, useState } from "react";
import type { ScannerEvent, TranscriptResult, TranscriptSegment } from "../lib/types";
import Tags from "./Tags";
import TranscriptPlayer from "./TranscriptPlayer";

interface Props {
  transcript: TranscriptResult;
  event?: ScannerEvent | null;
  searchQuery?: string;
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

export default function TranscriptPanel({ transcript, event, searchQuery, onClose }: Props) {
  const [visible] = useState(true);
  const [dragY, setDragY] = useState(0);
  const dragStartY = useRef(0);
  const dragging = useRef(false);
  const tags = transcript.tags;
  const segments = parseSegments(transcript.segments);
  const context = transcript.context || undefined;

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
    if (dragY > 100) {
      onClose();
    }
    setDragY(0);
  }, [dragY, onClose]);

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
          className="md:hidden flex justify-center pt-3 pb-1 cursor-grab active:cursor-grabbing"
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
        >
          <div className="w-10 h-1 rounded-full bg-[#3d444d]" />
        </div>

        <div className="shrink-0 border-b border-[#2d333b] px-4 py-3 flex justify-between items-center">
          <h3 className="font-medium text-sm text-[#e6edf3]">Transcript</h3>
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
            <FieldLabel>Time</FieldLabel>
            <div className="text-sm text-[#adbac7] tabular-nums">
              {formatDate(transcript.archive_ts)}
            </div>
          </div>

          <div>
            <FieldLabel>Feed</FieldLabel>
            <div className="text-sm text-[#adbac7]">
              {transcript.feed_name || transcript.feed_id}
            </div>
          </div>

          {event?.normalized && (
            <div>
              <FieldLabel>Location</FieldLabel>
              <div className="text-sm text-[#adbac7]">
                {event.normalized}
              </div>
            </div>
          )}

          {tags && (
            <div>
              <FieldLabel>Codes</FieldLabel>
              <Tags tags={tags} />
            </div>
          )}

          <div>
            <FieldLabel>Audio</FieldLabel>
            <TranscriptPlayer
              audioUrl={transcript.audio_url}
              segments={segments}
              context={context}
              searchQuery={searchQuery}
            />
          </div>

          {!segments.length && transcript.transcript && (
            <div>
              <FieldLabel>Text</FieldLabel>
              <div className="text-[13px] leading-relaxed text-[#adbac7]">
                {transcript.transcript}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
