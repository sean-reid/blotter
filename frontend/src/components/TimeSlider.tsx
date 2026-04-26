import "nouislider/dist/nouislider.css";
import noUiSlider, { type API } from "nouislider";
import { useEffect, useRef } from "react";
import type { TimeRange } from "../lib/types";

const PRESETS = [
  { label: "1 h", hours: 1 },
  { label: "6 h", hours: 6 },
  { label: "24 h", hours: 24 },
  { label: "7 d", hours: 168 },
] as const;

interface Props {
  range: TimeRange;
  onChange: (range: TimeRange) => void;
}

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function TimeSlider({ range, onChange }: Props) {
  const sliderRef = useRef<HTMLDivElement>(null);
  const apiRef = useRef<API | null>(null);

  useEffect(() => {
    if (!sliderRef.current || apiRef.current) return;

    const now = Math.floor(Date.now() / 1000);
    const weekAgo = now - 7 * 86400;

    const slider = noUiSlider.create(sliderRef.current, {
      start: [range.start, range.end],
      connect: true,
      range: { min: weekAgo, max: now },
      step: 300,
      behaviour: "drag",
    });

    slider.on("change", (values) => {
      onChange({
        start: Math.floor(Number(values[0])),
        end: Math.floor(Number(values[1])),
      });
    });

    apiRef.current = slider;

    return () => {
      slider.destroy();
      apiRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const setPreset = (hours: number) => {
    const now = Math.floor(Date.now() / 1000);
    const start = now - hours * 3600;
    apiRef.current?.set([start, now]);
    onChange({ start, end: now });
  };

  return (
    <div className="glass-panel rounded-t-2xl sm:rounded-xl shadow-xl mx-0 sm:mx-3 mb-0 sm:mb-3 px-4 py-3">
      <div className="flex items-center gap-3 mb-3">
        <span className="text-[11px] font-medium text-slate-400 shrink-0 tabular-nums tracking-tight min-w-[100px]">
          {formatTs(range.start)}
        </span>
        <div ref={sliderRef} className="flex-1" />
        <span className="text-[11px] font-medium text-slate-400 shrink-0 tabular-nums tracking-tight min-w-[100px] text-right">
          {formatTs(range.end)}
        </span>
      </div>

      <div className="flex gap-2 justify-center">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => setPreset(p.hours)}
            className="
              min-w-[48px] min-h-[36px] px-3 py-1.5
              text-xs font-medium tracking-wide text-slate-300
              rounded-lg
              bg-slate-800/60 border border-slate-700/40
              hover:bg-indigo-500/20 hover:text-indigo-300 hover:border-indigo-500/30
              active:scale-95
              transition-all duration-150
              select-none
            "
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}
