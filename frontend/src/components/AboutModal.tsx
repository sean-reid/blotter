import { useCallback, useEffect, useState } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function AboutModal({ open, onClose }: Props) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => setVisible(true));
    } else {
      setVisible(false);
    }
  }, [open]);

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className={`
        fixed inset-0 z-[100] flex items-center justify-center p-4
        transition-all duration-200
        ${visible ? "bg-black/50" : "bg-black/0 pointer-events-none"}
      `}
      onClick={handleBackdropClick}
    >
      <div
        className={`
          panel rounded-lg shadow-2xl
          w-full max-w-md max-h-[85vh] overflow-y-auto
          transition-all duration-200 ease-out
          ${visible ? "opacity-100 scale-100" : "opacity-0 scale-[0.98]"}
        `}
      >
        <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-[#2d333b]">
          <h2 className="text-sm font-semibold text-[#e6edf3]">
            About Blotter
          </h2>
          <button
            onClick={onClose}
            className="
              w-7 h-7 min-w-[44px] min-h-[44px]
              flex items-center justify-center
              rounded
              text-[#545d68] hover:text-[#adbac7]
              transition-colors duration-100
            "
            aria-label="Close"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="px-5 py-4 space-y-4 text-[13px] leading-relaxed text-[#adbac7]">
          <p>
            Blotter monitors public safety radio feeds across Los Angeles County,
            transcribes dispatch audio, extracts locations from the transcripts,
            and plots activity on a map in near real-time.
          </p>

          <div>
            <h3 className="text-[11px] font-medium uppercase tracking-wider text-[#545d68] mb-1.5">
              How it works
            </h3>
            <p>
              Live audio streams from Broadcastify are captured and transcribed
              using Faster Whisper on GPU. Google Cloud NLP extracts location
              references, which are geocoded via Google Places and plotted on the
              map. All transcripts and audio are searchable and playable.
            </p>
          </div>

          <div>
            <h3 className="text-[11px] font-medium uppercase tracking-wider text-[#545d68] mb-1.5">
              Stack
            </h3>
            <ul className="space-y-0.5 text-[#768390]">
              <li>Broadcastify live streams</li>
              <li>Faster Whisper (large-v3) on RunPod GPU</li>
              <li>Google Cloud NLP + Places API</li>
              <li>ClickHouse + Cloudflare Pages</li>
            </ul>
          </div>

          <div>
            <h3 className="text-[11px] font-medium uppercase tracking-wider text-[#545d68] mb-1.5">
              Built by
            </h3>
            <p>
              <a
                href="https://sean-reid.github.io"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#d4943a] hover:text-[#e0a550] underline underline-offset-2 transition-colors"
              >
                Sean Reid
              </a>
            </p>
          </div>

          <p className="text-[11px] text-[#545d68] border-t border-[#2d333b] pt-3">
            Locations are automatically extracted from audio transcriptions and
            may not be accurate. This tool is for informational purposes only.
          </p>
        </div>
      </div>
    </div>
  );
}
