import { useCallback, useEffect, useRef, useState } from "react";
import type { ScannerEvent, TranscriptResult, TranscriptSegment } from "../lib/types";
import { fetchSurroundingTranscripts } from "../lib/api";
import Tags from "./Tags";

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

interface FlatSegment {
  transcriptIdx: number;
  seg: TranscriptSegment;
  isFirstInCall: boolean;
  callTime: string;
  audioUrl: string;
  durationMs: number;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function buildFlatSegments(transcripts: TranscriptResult[]): FlatSegment[] {
  const flat: FlatSegment[] = [];
  for (let ti = 0; ti < transcripts.length; ti++) {
    const t = transcripts[ti]!;
    const segs = parseSegments(t.segments);
    const callTime = formatTime(t.archive_ts);
    for (let si = 0; si < segs.length; si++) {
      flat.push({
        transcriptIdx: ti,
        seg: segs[si]!,
        isFirstInCall: si === 0,
        callTime,
        audioUrl: t.audio_url,
        durationMs: t.duration_ms,
      });
    }
  }
  return flat;
}

export default function EventPanel({ event, onClose }: Props) {
  const [visible, setVisible] = useState(false);
  const [transcripts, setTranscripts] = useState<TranscriptResult[]>([]);
  const [flatSegments, setFlatSegments] = useState<FlatSegment[]>([]);
  const [loadingTranscript, setLoadingTranscript] = useState(false);
  const [dragY, setDragY] = useState(0);
  const dragStartY = useRef(0);
  const dragging = useRef(false);

  const [activeTranscriptIdx, setActiveTranscriptIdx] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);
  const [audioReady, setAudioReady] = useState(false);

  const ctxRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);
  const bufferRef = useRef<AudioBuffer | null>(null);
  const playStartRef = useRef(0);
  const offsetRef = useRef(0);
  const rafRef = useRef(0);
  const audioOffsetRef = useRef(0);
  const activeRef = useRef<HTMLDivElement>(null);
  const loadingUrlRef = useRef("");

  const stopSource = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    if (sourceRef.current) {
      try { sourceRef.current.stop(); } catch { /* */ }
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
  }, []);

  const tick = useCallback(() => {
    if (!sourceRef.current) return;
    const pos = offsetRef.current + (performance.now() - playStartRef.current) / 1000;
    setCurrentTime(pos);
    const effectiveDuration = bufferRef.current
      ? bufferRef.current.duration - audioOffsetRef.current : 0;
    if (bufferRef.current && pos >= effectiveDuration) {
      stopSource();
      offsetRef.current = effectiveDuration;
      setCurrentTime(effectiveDuration);
      setPlaying(false);
      return;
    }
    rafRef.current = requestAnimationFrame(tick);
  }, [stopSource]);

  const playFrom = useCallback((offset: number) => {
    const ctx = ctxRef.current;
    const buffer = bufferRef.current;
    if (!ctx || !buffer) return;
    stopSource();
    const audioPos = Math.max(0, Math.min(offset + audioOffsetRef.current, buffer.duration));
    const startSample = Math.floor(audioPos * buffer.sampleRate);
    const trimmedLength = buffer.length - startSample;
    if (trimmedLength <= 0) return;
    const trimmed = ctx.createBuffer(buffer.numberOfChannels, trimmedLength, buffer.sampleRate);
    for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
      trimmed.getChannelData(ch).set(buffer.getChannelData(ch).subarray(startSample));
    }
    const source = ctx.createBufferSource();
    source.buffer = trimmed;
    source.connect(ctx.destination);
    source.onended = () => {
      if (sourceRef.current === source) {
        cancelAnimationFrame(rafRef.current);
        sourceRef.current = null;
        setPlaying(false);
      }
    };
    sourceRef.current = source;
    offsetRef.current = offset;
    playStartRef.current = performance.now();
    source.start(0);
    setPlaying(true);
    rafRef.current = requestAnimationFrame(tick);
  }, [stopSource, tick]);

  const loadAndPlay = useCallback((audioUrl: string, durationMs: number, transcriptIdx: number, seekTo: number) => {
    if (!audioUrl) return;
    stopSource();
    setAudioReady(false);
    setPlaying(false);
    setActiveTranscriptIdx(transcriptIdx);
    bufferRef.current = null;
    loadingUrlRef.current = audioUrl;

    if (!ctxRef.current) ctxRef.current = new AudioContext();
    const ctx = ctxRef.current;
    if (ctx.state === "suspended") ctx.resume();

    fetch(audioUrl)
      .then((r) => { if (!r.ok) throw new Error(`${r.status}`); return r.arrayBuffer(); })
      .then((buf) => { if (loadingUrlRef.current !== audioUrl) return; return ctx.decodeAudioData(buf); })
      .then((decoded) => {
        if (!decoded || loadingUrlRef.current !== audioUrl) return;
        bufferRef.current = decoded;
        if (durationMs > 0) {
          const expected = durationMs / 1000;
          const diff = decoded.duration - expected;
          audioOffsetRef.current = diff > 5 ? diff : 0;
        } else {
          audioOffsetRef.current = 0;
        }
        setAudioDuration(decoded.duration - audioOffsetRef.current);
        setAudioReady(true);
        playFrom(seekTo);
      })
      .catch(() => {});
  }, [stopSource, playFrom]);

  const handleSegmentClick = useCallback((fs: FlatSegment) => {
    if (fs.transcriptIdx === activeTranscriptIdx && audioReady) {
      playFrom(fs.seg.start);
    } else {
      loadAndPlay(fs.audioUrl, fs.durationMs, fs.transcriptIdx, fs.seg.start);
    }
  }, [activeTranscriptIdx, audioReady, playFrom, loadAndPlay]);

  const togglePlay = useCallback(async () => {
    if (playing) {
      offsetRef.current += (performance.now() - playStartRef.current) / 1000;
      stopSource();
      setPlaying(false);
    } else if (audioReady) {
      if (ctxRef.current?.state === "suspended") await ctxRef.current.resume();
      playFrom(offsetRef.current);
    }
  }, [playing, audioReady, stopSource, playFrom]);

  useEffect(() => {
    if (event) {
      requestAnimationFrame(() => { setVisible(true); });
      setLoadingTranscript(true);
      setTranscripts([]);
      setFlatSegments([]);
      setDragY(0);
      setActiveTranscriptIdx(-1);
      setPlaying(false);
      setAudioReady(false);
      stopSource();
      fetchSurroundingTranscripts(event.feed_id, event.archive_ts)
        .then((results) => {
          setTranscripts(results);
          setFlatSegments(buildFlatSegments(results));
        })
        .catch(() => { setTranscripts([]); setFlatSegments([]); })
        .finally(() => setLoadingTranscript(false));
    } else {
      setVisible(false);
      setTranscripts([]);
      setFlatSegments([]);
      stopSource();
    }
  }, [event, stopSource]);

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
            <FieldLabel>Dispatch ({transcripts.length} calls)</FieldLabel>
            {loadingTranscript ? (
              <div className="text-xs text-[#545d68] italic">Loading...</div>
            ) : flatSegments.length > 0 ? (
              <div className="space-y-2">
                {audioReady && (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={togglePlay}
                      className="w-7 h-7 flex items-center justify-center rounded bg-[#2d333b] hover:bg-[#373e47] text-[#adbac7] transition-colors"
                    >
                      {playing ? (
                        <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                          <rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" />
                        </svg>
                      ) : (
                        <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M8 5v14l11-7z" />
                        </svg>
                      )}
                    </button>
                    <div
                      className="flex-1 h-1 bg-[#2d333b] rounded-full overflow-hidden cursor-pointer"
                      onClick={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        const pct = (e.clientX - rect.left) / rect.width;
                        const t = pct * audioDuration;
                        offsetRef.current = t;
                        setCurrentTime(t);
                        if (playing) playFrom(t);
                      }}
                    >
                      <div
                        className="h-full bg-[#539bf5] rounded-full"
                        style={{ width: `${audioDuration > 0 ? Math.min(1, currentTime / audioDuration) * 100 : 0}%` }}
                      />
                    </div>
                    <span className="text-[10px] tabular-nums text-[#545d68] min-w-[60px] text-right">
                      {formatDuration(currentTime)} / {formatDuration(audioDuration)}
                    </span>
                  </div>
                )}

                <div className="max-h-[400px] overflow-y-auto space-y-0">
                  {flatSegments.map((fs, i) => {
                    const isActive = fs.transcriptIdx === activeTranscriptIdx
                      && currentTime >= fs.seg.start && currentTime < fs.seg.end;
                    return (
                      <div key={i}>
                        {fs.isFirstInCall && (
                          <div className="flex items-center gap-2 py-1.5 mt-1 first:mt-0">
                            <span className="text-[10px] tabular-nums text-[#545d68]">{fs.callTime}</span>
                            <div className="flex-1 h-px bg-[#2d333b]" />
                          </div>
                        )}
                        <div
                          ref={isActive ? activeRef : undefined}
                          onClick={() => handleSegmentClick(fs)}
                          className={`
                            flex gap-2 px-2 py-1 rounded cursor-pointer
                            transition-colors duration-100
                            ${isActive
                              ? "bg-[#539bf5]/10 text-[#e6edf3]"
                              : "text-[#adbac7] hover:bg-[#2d333b]/50"
                            }
                          `}
                        >
                          <span className="text-[10px] tabular-nums text-[#545d68] pt-0.5 shrink-0">
                            {formatDuration(fs.seg.start)}
                          </span>
                          <span className="text-[12px] leading-relaxed">{fs.seg.text}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
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
