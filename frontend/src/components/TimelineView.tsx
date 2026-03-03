import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import SourceBadge from "./SourceBadge";

export interface TimelineEvent {
  id: string;
  date: string;
  title: string;
  description: string;
  category: "financial" | "social" | "breach" | "news" | "personal" | "company";
  source: string;
  details?: Record<string, any>;
}

interface TimelineViewProps {
  events: TimelineEvent[];
  className?: string;
}

const categoryConfig: Record<
  string,
  { color: string; dotColor: string; lineColor: string }
> = {
  financial: {
    color: "text-emerald-400",
    dotColor: "bg-emerald-500",
    lineColor: "border-emerald-500/30",
  },
  social: {
    color: "text-blue-400",
    dotColor: "bg-blue-500",
    lineColor: "border-blue-500/30",
  },
  breach: {
    color: "text-red-400",
    dotColor: "bg-red-500",
    lineColor: "border-red-500/30",
  },
  news: {
    color: "text-purple-400",
    dotColor: "bg-purple-500",
    lineColor: "border-purple-500/30",
  },
  personal: {
    color: "text-sky-400",
    dotColor: "bg-sky-500",
    lineColor: "border-sky-500/30",
  },
  company: {
    color: "text-emerald-300",
    dotColor: "bg-emerald-400",
    lineColor: "border-emerald-400/30",
  },
};

function TimelineItem({ event }: { event: TimelineEvent }) {
  const [expanded, setExpanded] = useState(false);
  const config = categoryConfig[event.category] || categoryConfig.personal;

  return (
    <div className="relative flex gap-4 pb-6 last:pb-0 animate-fade-in">
      {/* Timeline line */}
      <div className="absolute left-[11px] top-6 bottom-0 w-px bg-zinc-800 last:hidden" />

      {/* Dot */}
      <div className="relative z-10 shrink-0 mt-1">
        <div
          className={`w-[22px] h-[22px] rounded-full border-2 border-zinc-900 ${config.dotColor} flex items-center justify-center`}
        >
          <div className="w-2 h-2 rounded-full bg-zinc-950" />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Date label */}
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-mono text-zinc-500">
            {event.date
              ? new Date(event.date).toLocaleDateString("sv-SE", {
                  year: "numeric",
                  month: "short",
                  day: "numeric",
                })
              : "Unknown date"}
          </span>
          <span
            className={`text-xs font-medium uppercase tracking-wider ${config.color}`}
          >
            {event.category}
          </span>
        </div>

        {/* Card */}
        <div
          className={`bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 cursor-pointer hover:border-zinc-700 transition-colors`}
          onClick={() => setExpanded(!expanded)}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-medium text-zinc-200">
                {event.title}
              </h4>
              <p className="text-xs text-zinc-400 mt-0.5 leading-relaxed">
                {event.description}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <SourceBadge source={event.source} />
              {event.details && (
                <button className="text-zinc-500 hover:text-zinc-300">
                  {expanded ? (
                    <ChevronDown className="w-4 h-4" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                </button>
              )}
            </div>
          </div>

          {/* Expanded details */}
          {expanded && event.details && (
            <div className="mt-3 pt-3 border-t border-zinc-800">
              <dl className="grid grid-cols-2 gap-2">
                {Object.entries(event.details).map(([key, value]) => (
                  <div key={key}>
                    <dt className="text-xs text-zinc-500 capitalize">
                      {key.replace(/_/g, " ")}
                    </dt>
                    <dd className="text-xs font-mono text-zinc-300 mt-0.5">
                      {String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function TimelineView({
  events,
  className = "",
}: TimelineViewProps) {
  const sorted = [...events].sort(
    (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
  );

  if (sorted.length === 0) {
    return (
      <div
        className={`flex items-center justify-center text-zinc-500 text-sm py-12 ${className}`}
      >
        No timeline events to display
      </div>
    );
  }

  return (
    <div className={`pl-1 ${className}`}>
      {sorted.map((event) => (
        <TimelineItem key={event.id} event={event} />
      ))}
    </div>
  );
}
