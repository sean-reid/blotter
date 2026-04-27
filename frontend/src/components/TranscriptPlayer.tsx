import { useEffect, useRef, useState } from "react";
import type { TranscriptSegment } from "../lib/types";

interface Props {
  audioUrl: string;
  segments: TranscriptSegment[];
  context?: string;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const CONTEXT_PAD = 10;

function findContextRange(
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
    const half = Math.floor(contextWords.length / 2);
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

export default function TranscriptPlayer({ audioUrl, segments, context }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const activeRef = useRef<HTMLDivElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [audioError, setAudioError] = useState(false);
  const [ready, setReady] = useState(false);
  const [audioDuration, setAudioDuration] = useState(0);

  const range = context ? findContextRange(segments, context) : null;
  const startTime = range?.startTime ?? 0;
  const segEndTime = range?.endTime ?? (segments.length > 0 ? segments[segments.length - 1]!.end : 0);
  const endTime = audioDuration > 0
    ? (segEndTime > 0 ? Math.min(segEndTime, audioDuration) : audioDuration)
    : segEndTime;
  const clipDuration = endTime - startTime;

  const visibleSegments = range
    ? segments.slice(range.startIdx, range.endIdx + 1)
    : segments;

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTime = () => {
      setCurrentTime(audio.currentTime);
      if (range && audio.currentTime >= range.endTime) {
        audio.pause();
      }
    };
    const onCanPlay = () => {
      setReady(true);
      if (range) audio.currentTime = range.startTime;
    };
    const onMeta = () => {
      if (audio.duration && isFinite(audio.duration)) {
        setAudioDuration(audio.duration);
      }
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onError = () => setAudioError(true);

    audio.addEventListener("timeupdate", onTime);
    audio.addEventListener("canplay", onCanPlay);
    audio.addEventListener("loadedmetadata", onMeta);
    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("error", onError);

    return () => {
      audio.removeEventListener("timeupdate", onTime);
      audio.removeEventListener("canplay", onCanPlay);
      audio.removeEventListener("loadedmetadata", onMeta);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("error", onError);
    };
  }, [range?.startTime, range?.endTime]);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [currentTime]);

  const activeIndex = visibleSegments.findIndex(
    (s) => currentTime >= s.start && currentTime < s.end,
  );

  const seekTo = (time: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = time;
    }
  };

  const togglePlay = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
    } else {
      if (range && audio.currentTime >= range.endTime) {
        audio.currentTime = range.startTime;
      }
      audio.play();
    }
  };

  const elapsed = Math.max(0, currentTime - startTime);
  const progress = clipDuration > 0 ? Math.min(1, elapsed / clipDuration) : 0;

  if (!audioUrl && !visibleSegments.length) return null;

  return (
    <div className="space-y-3">
      {audioUrl && !audioError && (
        <div className="space-y-2">
          <audio ref={audioRef} src={audioUrl} preload="auto" />

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
