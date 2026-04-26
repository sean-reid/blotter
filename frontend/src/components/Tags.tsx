const CODE_LABELS: Record<string, string> = {
  "code 1": "No lights/sirens",
  "code 2": "Urgent",
  "code 3": "Emergency",
  "code 4": "No further assist",
  "code 5": "Stakeout",
  "code 6": "Out for investigation",
  "code 7": "Meal break",
  "code 37": "Stolen vehicle",
  "10-4": "Acknowledged",
  "10-7": "Out of service",
  "10-8": "In service",
  "10-15": "Prisoner in custody",
  "10-20": "Location",
  "10-29": "Check wants",
  "10-33": "Emergency traffic",
  "10-77": "ETA",
  "10-97": "Arrived at scene",
  "10-98": "Available",
  "10-99": "Wanted person",
  "187": "Homicide",
  "207": "Kidnapping",
  "211": "Robbery",
  "242": "Battery",
  "245": "ADW",
  "261": "Rape",
  "415": "Disturb. peace",
  "459": "Burglary",
  "484": "Theft",
  "487": "Grand theft",
  "502": "DUI",
  "647": "Disorderly",
  "10851": "Stolen vehicle",
  "11-44": "Deceased",
  "11-80": "Major accident",
  "11-99": "Officer needs help",
};

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
        const storedLabel = colonIdx > -1 ? raw.slice(colonIdx + 1) : "";
        const label = storedLabel || CODE_LABELS[code.toLowerCase()] || "";
        return (
          <span
            key={raw}
            className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#2d333b] text-[#adbac7]"
            title={label || undefined}
          >
            {code}
            {label && (
              <span className="ml-1 text-[#545d68]">{label}</span>
            )}
          </span>
        );
      })}
    </div>
  );
}
