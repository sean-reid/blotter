import { useEffect, useState } from "react";
import type { ScannerEvent, TranscriptResult } from "../lib/types";

interface Props {
  event: ScannerEvent | null;
  transcript: TranscriptResult | null;
  onClose: () => void;
}

function formatDate(ts: string): string {
  return new Date(ts).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-1">
      {children}
    </div>
  );
}

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <span className="text-sm tabular-nums text-slate-200">{pct}%</span>
  );
}

export default function EventPanel({ event, transcript, onClose }: Props) {
  const [visible, setVisible] = useState(false);
  const hasContent = !!(event || transcript);

  useEffect(() => {
    if (hasContent) {
      // Small delay to allow the DOM to render before animating
      requestAnimationFrame(() => { setVisible(true); });
    } else {
      setVisible(false);
    }
  }, [hasContent]);

  if (!hasContent) return null;

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
          md:top-0 md:right-0 md:left-auto md:bottom-0 md:w-[400px]

          glass-panel
          rounded-t-2xl md:rounded-none md:border-l md:border-t-0

          max-h-[70vh] md:max-h-full
          overflow-hidden
          flex flex-col

          transition-transform duration-350 ease-out
          ${visible
            ? "translate-y-0 md:translate-x-0"
            : "translate-y-full md:translate-y-0 md:translate-x-full"
          }
        `}
        style={{ transitionTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)" }}
      >
        <div className="md:hidden flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full bg-slate-600" />
        </div>

        <div className="shrink-0 border-b border-slate-700/40 px-5 py-3.5 flex justify-between items-center">
          <h3 className="font-semibold text-sm text-slate-100 tracking-tight">
            {event ? "Event Details" : "Transcript"}
          </h3>
          <button
            onClick={onClose}
            className="
              w-8 h-8 min-w-[44px] min-h-[44px]
              flex items-center justify-center
              rounded-lg
              text-slate-400 hover:text-slate-200
              hover:bg-slate-700/50
              transition-colors duration-150
            "
            aria-label="Close panel"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {event && (
            <>
              <div>
                <FieldLabel>Location</FieldLabel>
                <div className="text-sm font-medium text-slate-100 leading-snug">
                  {event.normalized}
                </div>
                {event.raw_location !== event.normalized && (
                  <div className="text-xs text-slate-500 mt-0.5">
                    Raw: {event.raw_location}
                  </div>
                )}
              </div>

              <div className="flex gap-6">
                <div className="flex-1">
                  <FieldLabel>Time</FieldLabel>
                  <div className="text-sm text-slate-200 tabular-nums">
                    {formatDate(event.event_ts)}
                  </div>
                </div>
                <div>
                  <FieldLabel>Confidence</FieldLabel>
                  <ConfidenceBadge value={event.confidence} />
                </div>
              </div>

              <div>
                <FieldLabel>Feed</FieldLabel>
                <div className="text-sm text-slate-200">{event.feed_id}</div>
              </div>
            </>
          )}

          {transcript && (
            <>
              <div>
                <FieldLabel>Feed</FieldLabel>
                <div className="text-sm font-medium text-slate-100">
                  {transcript.feed_name}
                </div>
              </div>

              <div>
                <FieldLabel>Time</FieldLabel>
                <div className="text-sm text-slate-200 tabular-nums">
                  {formatDate(transcript.archive_ts)}
                </div>
              </div>

              {transcript.audio_url && (
                <div>
                  <FieldLabel>Audio</FieldLabel>
                  <audio
                    controls
                    src={transcript.audio_url}
                    className="w-full h-10 mt-1 rounded-lg"
                    style={{
                      filter: "invert(1) hue-rotate(180deg)",
                      opacity: 0.85,
                    }}
                  />
                </div>
              )}

              <div>
                <FieldLabel>Transcript</FieldLabel>
                <div className="
                  text-sm leading-relaxed text-slate-300 whitespace-pre-wrap
                  bg-slate-800/50 border border-slate-700/30 rounded-lg
                  p-3 mt-1
                  max-h-64 overflow-y-auto
                ">
                  {transcript.transcript}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
