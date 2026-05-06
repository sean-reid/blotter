interface Props {
  tags: string;
}

export default function Tags({ tags }: Props) {
  if (!tags) return null;
  const list = tags.split(",").map((t) => t.trim()).filter(Boolean);
  if (!list.length) return null;

  return (
    <div className="flex flex-wrap gap-1">
      {list.map((raw) => {
        const colonIdx = raw.indexOf(":");
        const code = colonIdx > -1 ? raw.slice(0, colonIdx) : raw;
        const label = colonIdx > -1 ? raw.slice(colonIdx + 1) : "";
        return (
          <span
            key={raw}
            className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#2d333b] text-[#adbac7]"
          >
            {code}
            {label && (
              <span className="ml-1 text-[#768390]">({label})</span>
            )}
          </span>
        );
      })}
    </div>
  );
}
