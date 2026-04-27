import { useEffect, useState } from "react";
import type { ScannerEvent, TranscriptResult, TranscriptSegment } from "../lib/types";
import { fetchEventForTranscript } from "../lib/api";
import Tags from "./Tags";
import TranscriptPlayer from "./TranscriptPlayer";

interface Props {
  transcript: TranscriptResult;
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

export default function TranscriptPanel({ transcript, onClose }: Props) {
  const [visible] = useState(true);
  const [event, setEvent] = useState<ScannerEvent | null>(null);

  useEffect(() => {
    setEvent(null);
    fetchEventForTranscript(transcript.feed_id, transcript.archive_ts)
      .then(setEvent)
      .catch(() => setEvent(null));
  }, [transcript.feed_id, transcript.archive_ts]);

  const tags = transcript.tags || event?.tags;

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

          transition-transform duration-300
          ${visible
            ? "translate-y-0 md:translate-x-0"
            : "translate-y-full md:translate-y-0 md:translate-x-full"
          }
        `}
        style={{ transitionTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)" }}
      >
        <div className="md:hidden flex justify-center pt-3 pb-1">
          <div className="w-8 h-0.5 rounded-full bg-[#2d333b]" />
        </div>

        <div className="shrink-0 border-b border-[#2d333b] px-4 py-3 flex justify-between items-center">
          <h3 className="font-medium text-sm text-[#e6edf3]">
            {event ? "Event" : "Transcript"}
          </h3>
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
          {event && (
            <div>
              <FieldLabel>Location</FieldLabel>
              <div className="text-sm font-medium text-[#e6edf3] leading-snug">
                {event.normalized}
              </div>
              <div className="text-[11px] text-[#545d68] tabular-nums font-mono mt-1">
                {event.latitude.toFixed(5)}, {event.longitude.toFixed(5)}
              </div>
            </div>
          )}

          <div className="flex gap-6">
            <div className="flex-1">
              <FieldLabel>Time</FieldLabel>
              <div className="text-sm text-[#adbac7] tabular-nums">
                {formatDate(event?.event_ts ?? transcript.archive_ts)}
              </div>
            </div>
            {event && (
              <div>
                <FieldLabel>Confidence</FieldLabel>
                <span className="text-sm tabular-nums text-[#adbac7]">
                  {Math.round(event.confidence * 100)}%
                </span>
              </div>
            )}
          </div>

          <div>
            <FieldLabel>Feed</FieldLabel>
            <div className="text-sm text-[#adbac7]">
              {transcript.feed_name || transcript.feed_id}
            </div>
          </div>

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
              segments={parseSegments(transcript.segments)}
              context={event?.context}
            />
          </div>

          {!parseSegments(transcript.segments).length && transcript.transcript && (
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
