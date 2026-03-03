import { Loader2, CheckCircle2, XCircle, Clock, Database } from "lucide-react";
import type { AgentProgress } from "../stores/investigation";

interface SwarmFeedProps {
  progress: AgentProgress[];
  className?: string;
}

const statusConfig: Record<
  string,
  { icon: typeof Loader2; color: string; animate?: string }
> = {
  running: {
    icon: Loader2,
    color: "text-sky-400",
    animate: "animate-spin",
  },
  completed: {
    icon: CheckCircle2,
    color: "text-emerald-400",
  },
  failed: {
    icon: XCircle,
    color: "text-red-400",
  },
  queued: {
    icon: Clock,
    color: "text-zinc-500",
  },
};

export default function SwarmFeed({ progress, className = "" }: SwarmFeedProps) {
  if (progress.length === 0) {
    return (
      <div
        className={`flex items-center justify-center text-zinc-500 text-sm py-8 ${className}`}
      >
        Waiting for agent updates...
      </div>
    );
  }

  return (
    <div className={`space-y-2 ${className}`}>
      {progress.map((event, idx) => {
        const config = statusConfig[event.status] || statusConfig.queued;
        const Icon = config.icon;

        return (
          <div
            key={event.id || idx}
            className="flex items-start gap-3 p-3 bg-zinc-900/50 border border-zinc-800/50 rounded-lg animate-slide-up"
          >
            {/* Status icon */}
            <div className="mt-0.5 shrink-0">
              <Icon
                className={`w-4 h-4 ${config.color} ${config.animate || ""}`}
              />
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
                  {event.agent_name}
                </span>
                {event.status === "running" && (
                  <span className="inline-flex h-1.5 w-1.5 rounded-full bg-sky-400 animate-pulse-slow" />
                )}
              </div>
              <p className="text-sm text-zinc-400 mt-0.5 leading-relaxed">
                {event.message}
              </p>

              {/* Facts found */}
              {event.facts_found > 0 && (
                <div className="flex items-center gap-1.5 mt-1.5">
                  <Database className="w-3 h-3 text-emerald-500" />
                  <span className="text-xs font-mono text-emerald-400">
                    +{event.facts_found} facts
                  </span>
                </div>
              )}
            </div>

            {/* Timestamp */}
            <span className="text-xs text-zinc-600 font-mono shrink-0">
              {event.timestamp
                ? new Date(event.timestamp).toLocaleTimeString("sv-SE", {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })
                : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}
