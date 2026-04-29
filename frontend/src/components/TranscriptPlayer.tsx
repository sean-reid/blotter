import { useCallback, useEffect, useRef, useState } from "react";
import type { TranscriptSegment } from "../lib/types";

interface Props {
  audioUrl: string;
  segments: TranscriptSegment[];
  context?: string;
  searchQuery?: string;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const CONTEXT_PAD = 10;

function findRangeByQuery(
  segments: TranscriptSegment[],
  query: string,
): { startTime: number; endTime: number; startIdx: number; endIdx: number } | null {
  if (!segments.length || !query) return null;

  const queryLower = query.toLowerCase().trim();
  if (!queryLower) return null;

  let matchIdx = -1;
  for (let i = 0; i < segments.length; i++) {
    if (segments[i]!.text.toLowerCase().includes(queryLower)) {
      matchIdx = i;
      break;
    }
  }

  if (matchIdx === -1) {
    const queryWords = queryLower.split(/\s+/);
    if (queryWords.length > 1) {
      for (let i = 0; i < segments.length; i++) {
        const segLower = segments[i]!.text.toLowerCase();
        if (queryWords.every((w) => segLower.includes(w))) {
          matchIdx = i;
          break;
        }
      }
    }
  }

  if (matchIdx === -1) return null;

  const padStart = Math.max(0, matchIdx - 2);
  const padEnd = Math.min(segments.length - 1, matchIdx + 3);
  return {
    startTime: Math.max(0, segments[padStart]!.start - CONTEXT_PAD),
    endTime: segments[padEnd]!.end + CONTEXT_PAD,
    startIdx: padStart,
    endIdx: padEnd,
  };
}

function findRangeByContext(
  segments: TranscriptSegment[],
  context: string,
): { startTime: number; endTime: number; startIdx: number; endIdx: number } | null {
  if (!segments.length || !context) return null;

  const contextLower = context.replace(/^\.{3}/, "").replace(/\.{3}$/, "").toLowerCase().trim();
  if (!contextLower) return null;

  const segOffsets: { idx: number; charStart: number; charEnd: number }[] = [];
  let fullText = "";
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    if (!seg) continue;
    const start = fullText.length;
    fullText += (fullText ? " " : "") + seg.text.toLowerCase();
    segOffsets.push({ idx: i, charStart: start, charEnd: fullText.length });
  }

  const contextWords = contextLower.split(/\s+/).filter(Boolean);
  let matchStart = -1;
  let matchEnd = -1;

  const searchStr = contextWords.join(" ");
  const pos = fullText.indexOf(searchStr);
  if (pos !== -1) {
    matchStart = pos;
    matchEnd = pos + searchStr.length;
  } else {
    for (let len = contextWords.length; len >= Math.min(4, contextWords.length); len--) {
      const sub = contextWords.slice(0, len).join(" ");
      const p = fullText.indexOf(sub);
      if (p !== -1) {
        matchStart = p;
        matchEnd = p + sub.length;
        break;
      }
    }
    if (matchStart === -1) {
      const half = Math.floor(contextWords.length / 2);
      for (let len = half; len >= Math.min(4, contextWords.length); len--) {
        const sub = contextWords.slice(-len).join(" ");
        const p = fullText.indexOf(sub);
        if (p !== -1) {
          matchStart = p;
          matchEnd = p + sub.length;
          break;
        }
      }
    }
  }

  if (matchStart === -1) {
    let best = -1;
    let bestScore = 0;
    const ctxSet = new Set(contextWords);
    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      if (!seg) continue;
      const words = seg.text.toLowerCase().split(/\s+/);
      const score = words.filter((w) => ctxSet.has(w)).length;
      if (score > bestScore) {
        bestScore = score;
        best = i;
      }
    }
    if (best === -1 || bestScore < 2) return null;
    const padStart = Math.max(0, best - 2);
    const padEnd = Math.min(segments.length - 1, best + 2);
    return {
      startTime: Math.max(0, segments[padStart]!.start - CONTEXT_PAD),
      endTime: segments[padEnd]!.end + CONTEXT_PAD,
      startIdx: padStart,
      endIdx: padEnd,
    };
  }

  let startIdx = 0;
  let endIdx = segments.length - 1;
  for (const so of segOffsets) {
    if (so.charEnd > matchStart) { startIdx = so.idx; break; }
  }
  for (let i = segOffsets.length - 1; i >= 0; i--) {
    if (segOffsets[i]!.charStart < matchEnd) { endIdx = segOffsets[i]!.idx; break; }
  }

  const padStart = Math.max(0, startIdx - 1);
  const padEnd = Math.min(segments.length - 1, endIdx + 1);

  return {
    startTime: Math.max(0, segments[padStart]!.start - CONTEXT_PAD),
    endTime: segments[padEnd]!.end + CONTEXT_PAD,
    startIdx: padStart,
    endIdx: padEnd,
  };
}

export default function TranscriptPlayer({ audioUrl, segments, context, searchQuery }: Props) {
  const activeRef = useRef<HTMLDivElement>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);
  const bufferRef = useRef<AudioBuffer | null>(null);
  const playStartRef = useRef(0);
  const offsetRef = useRef(0);
  const rafRef = useRef(0);

  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [audioError, setAudioError] = useState(false);
  const [ready, setReady] = useState(false);
  const [audioDuration, setAudioDuration] = useState(0);

  const range =
    (searchQuery ? findRangeByQuery(segments, searchQuery) : null)
    ?? (context ? findRangeByContext(segments, context) : null);

  const startTime = range?.startTime ?? 0;
  const endTime = range
    ? (audioDuration > 0 ? Math.min(range.endTime, audioDuration) : range.endTime)
    : (audioDuration > 0 ? audioDuration : (segments.length > 0 ? segments[segments.length - 1]!.end : 0));
  const clipDuration = endTime - startTime;

  const visibleSegments = range
    ? segments.slice(range.startIdx, range.endIdx + 1)
    : segments;

  const stopSource = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    if (sourceRef.current) {
      try { sourceRef.current.stop(); } catch { /* already stopped */ }
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
  }, []);

  const tick = useCallback(() => {
    const ctx = ctxRef.current;
    if (!ctx || !sourceRef.current) return;
    const pos = offsetRef.current + (ctx.currentTime - playStartRef.current);
    setCurrentTime(pos);
    if (range && pos >= range.endTime) {
      stopSource();
      offsetRef.current = range.endTime;
      setPlaying(false);
      return;
    }
    if (bufferRef.current && pos >= bufferRef.current.duration) {
      stopSource();
      offsetRef.current = bufferRef.current.duration;
      setPlaying(false);
      return;
    }
    rafRef.current = requestAnimationFrame(tick);
  }, [range, stopSource]);

  const playFrom = useCallback((offset: number) => {
    const ctx = ctxRef.current;
    const buffer = bufferRef.current;
    if (!ctx || !buffer) return;
    stopSource();
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    source.onended = () => {
      if (sourceRef.current === source) {
        setPlaying(false);
        cancelAnimationFrame(rafRef.current);
      }
    };
    const clampedOffset = Math.max(0, Math.min(offset, buffer.duration));
    sourceRef.current = source;
    offsetRef.current = clampedOffset;
    playStartRef.current = ctx.currentTime;
    source.start(0, clampedOffset);
    setPlaying(true);
    rafRef.current = requestAnimationFrame(tick);
  }, [stopSource, tick]);

  useEffect(() => {
    if (!audioUrl) return;
    let cancelled = false;
    setReady(false);
    setAudioError(false);
    setPlaying(false);
    stopSource();
    bufferRef.current = null;

    if (!ctxRef.current) {
      ctxRef.current = new AudioContext();
    }
    const ctx = ctxRef.current;

    fetch(audioUrl)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.arrayBuffer();
      })
      .then((buf) => {
        if (cancelled) return;
        return ctx.decodeAudioData(buf);
      })
      .then((decoded) => {
        if (cancelled || !decoded) return;
        bufferRef.current = decoded;
        setAudioDuration(decoded.duration);
        setReady(true);
      })
      .catch(() => {
        if (!cancelled) setAudioError(true);
      });

    return () => {
      cancelled = true;
      stopSource();
    };
  }, [audioUrl, stopSource]);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [currentTime]);

  const activeIndex = visibleSegments.findIndex(
    (s) => currentTime >= s.start && currentTime < s.end,
  );

  const seekTo = useCallback((time: number) => {
    offsetRef.current = time;
    setCurrentTime(time);
    if (playing) {
      playFrom(time);
    }
  }, [playing, playFrom]);

  const togglePlay = useCallback(async () => {
    if (playing) {
      const ctx = ctxRef.current;
      if (ctx) {
        offsetRef.current += ctx.currentTime - playStartRef.current;
      }
      stopSource();
      setPlaying(false);
    } else {
      let offset = offsetRef.current;
      if (range && offset >= range.endTime) {
        offset = range.startTime;
      }
      if (ctxRef.current?.state === "suspended") {
        await ctxRef.current.resume();
      }
      playFrom(offset);
    }
  }, [playing, range, stopSource, playFrom]);

  useEffect(() => {
    if (ready && range) {
      offsetRef.current = range.startTime;
      setCurrentTime(range.startTime);
    }
  }, [ready, range?.startTime]);

  const elapsed = Math.max(0, currentTime - startTime);
  const progress = clipDuration > 0 ? Math.min(1, elapsed / clipDuration) : 0;

  if (!audioUrl && !visibleSegments.length) return null;

  return (
    <div className="space-y-3">
      {audioUrl && !audioError && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <button
              onClick={togglePlay}
              disabled={!ready}
              className="
                w-7 h-7 flex items-center justify-center rounded
                bg-[#2d333b] hover:bg-[#373e47]
                text-[#adbac7] transition-colors
                disabled:opacity-40
              "
            >
              {playing ? (
                <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                  <rect x="6" y="4" width="4" height="16" />
                  <rect x="14" y="4" width="4" height="16" />
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
                seekTo(startTime + pct * clipDuration);
              }}
            >
              <div
                className="h-full bg-[#539bf5] rounded-full transition-[width] duration-100"
                style={{ width: `${progress * 100}%` }}
              />
            </div>

            <span className="text-[10px] tabular-nums text-[#545d68] min-w-[60px] text-right">
              {formatTime(elapsed)} / {formatTime(clipDuration)}
            </span>
          </div>
        </div>
      )}

      {audioError && (
        <div className="text-xs text-[#545d68] italic">Audio unavailable</div>
      )}

      {visibleSegments.length > 0 && (
        <div className={`${range ? "max-h-[160px]" : "max-h-[300px]"} overflow-y-auto space-y-0.5 scrollbar-thin`}>
          {visibleSegments.map((seg, i) => (
            <div
              key={i}
              ref={i === activeIndex ? activeRef : undefined}
              onClick={() => seekTo(seg.start)}
              className={`
                flex gap-2 px-2 py-1 rounded cursor-pointer
                transition-colors duration-100
                ${i === activeIndex
                  ? "bg-[#539bf5]/10 text-[#e6edf3]"
                  : "text-[#adbac7] hover:bg-[#2d333b]/50"
                }
              `}
            >
              <span className="text-[10px] tabular-nums text-[#545d68] pt-0.5 shrink-0">
                {formatTime(seg.start)}
              </span>
              <span className="text-[12px] leading-relaxed">{seg.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
