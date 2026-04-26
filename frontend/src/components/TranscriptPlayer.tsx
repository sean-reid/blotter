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

  const contextWords = contextLower.split(/\s+/).filter(Boolean);
  if (contextWords.length < 3) return null;

  const firstFew = contextWords.slice(0, 5).join(" ");
  const lastFew = contextWords.slice(-5).join(" ");

  let bestStart = -1;
  let bestEnd = -1;

  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    if (!seg) continue;
    const segLower = seg.text.toLowerCase();
    if (bestStart === -1 && segLower.includes(firstFew.slice(0, 30))) {
      bestStart = i;
    }
    if (segLower.includes(lastFew.slice(-30))) {
      bestEnd = i;
    }
  }

  if (bestStart === -1) {
    let maxOverlap = 0;
    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      if (!seg) continue;
      const segWords = new Set(seg.text.toLowerCase().split(/\s+/));
      const overlap = contextWords.filter((w) => segWords.has(w)).length;
      if (overlap > maxOverlap) {
        maxOverlap = overlap;
        bestStart = i;
      }
    }
  }

  if (bestStart === -1) return null;
  if (bestEnd === -1 || bestEnd < bestStart) bestEnd = bestStart;

  const padStart = Math.max(0, bestStart - 1);
  const padEnd = Math.min(segments.length - 1, bestEnd + 1);

  const startSeg = segments[padStart];
  const endSeg = segments[padEnd];
  if (!startSeg || !endSeg) return null;

  return {
    startTime: Math.max(0, startSeg.start - CONTEXT_PAD),
    endTime: endSeg.end + CONTEXT_PAD,
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
