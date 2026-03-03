import SourceBadge from "./SourceBadge";

interface FactCardProps {
  content: string;
  source: string;
  timestamp: string;
  confidence: number;
  category?: string;
  className?: string;
}

const categoryColors: Record<string, string> = {
  financial: "border-l-emerald-500",
  social: "border-l-blue-500",
  breach: "border-l-red-500",
  news: "border-l-purple-500",
  personal: "border-l-sky-500",
  company: "border-l-emerald-400",
  contact: "border-l-amber-500",
  address: "border-l-amber-400",
};

export default function FactCard({
  content,
  source,
  timestamp,
  confidence,
  category,
  className = "",
}: FactCardProps) {
  const borderColor = category
    ? categoryColors[category] || "border-l-zinc-600"
    : "border-l-zinc-600";

  const confidencePercent = Math.round(confidence * 100);
  const confidenceColor =
    confidencePercent >= 80
      ? "bg-emerald-500"
      : confidencePercent >= 50
      ? "bg-amber-500"
      : "bg-red-500";

  return (
    <div
      className={`bg-zinc-900/60 border border-zinc-800 border-l-2 ${borderColor} rounded-lg p-3.5 animate-fade-in ${className}`}
    >
      {/* Content */}
      <p className="text-sm text-zinc-200 leading-relaxed">{content}</p>

      {/* Footer */}
      <div className="flex items-center justify-between mt-3 gap-3">
        <div className="flex items-center gap-2">
          <SourceBadge source={source} />
          {category && (
            <span className="text-xs text-zinc-500 capitalize">{category}</span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Confidence bar */}
          <div className="flex items-center gap-1.5">
            <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${confidenceColor} transition-all duration-500`}
                style={{ width: `${confidencePercent}%` }}
              />
            </div>
            <span className="text-xs font-mono text-zinc-500">
              {confidencePercent}%
            </span>
          </div>

          {/* Timestamp */}
          <span className="text-xs text-zinc-600 font-mono">
            {timestamp
              ? new Date(timestamp).toLocaleDateString("sv-SE")
              : ""}
          </span>
        </div>
      </div>
    </div>
  );
}
