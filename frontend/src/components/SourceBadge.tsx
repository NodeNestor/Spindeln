interface SourceBadgeProps {
  source: string;
  className?: string;
}

const sourceColors: Record<string, { bg: string; text: string }> = {
  ratsit: { bg: "bg-orange-500/15", text: "text-orange-400" },
  hitta: { bg: "bg-blue-500/15", text: "text-blue-400" },
  eniro: { bg: "bg-cyan-500/15", text: "text-cyan-400" },
  allabolag: { bg: "bg-emerald-500/15", text: "text-emerald-400" },
  birthday: { bg: "bg-pink-500/15", text: "text-pink-400" },
  merinfo: { bg: "bg-violet-500/15", text: "text-violet-400" },
  lexbase: { bg: "bg-red-500/15", text: "text-red-400" },
  google: { bg: "bg-yellow-500/15", text: "text-yellow-400" },
  facebook: { bg: "bg-blue-600/15", text: "text-blue-300" },
  linkedin: { bg: "bg-sky-500/15", text: "text-sky-400" },
  hibp: { bg: "bg-red-500/15", text: "text-red-400" },
  flashback: { bg: "bg-amber-500/15", text: "text-amber-400" },
};

const defaultColor = { bg: "bg-zinc-700/30", text: "text-zinc-400" };

export default function SourceBadge({ source, className = "" }: SourceBadgeProps) {
  const key = source.toLowerCase().replace(/[^a-z]/g, "");
  const colors = sourceColors[key] || defaultColor;

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text} ${className}`}
    >
      {source}
    </span>
  );
}
