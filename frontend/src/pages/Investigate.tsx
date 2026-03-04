import { useState } from "react";
import {
  Radar,
  Play,
  Square,
  Wifi,
  WifiOff,
  Trash2,
  Database,
  Clock,
  User,
  ExternalLink,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useInvestigationStore } from "../stores/investigation";
import SwarmFeed from "../components/SwarmFeed";

const categoryOptions = [
  { value: "", label: "All categories (full investigation)" },
  { value: "personal", label: "Personal data only" },
  { value: "financial", label: "Financial data only" },
  { value: "companies", label: "Company data only" },
  { value: "social", label: "Social media only" },
  { value: "breach", label: "Breach data only" },
];

export default function Investigate() {
  const [target, setTarget] = useState("");
  const [category, setCategory] = useState("");

  const navigate = useNavigate();

  const {
    session,
    progress,
    isConnected,
    isStarting,
    error,
    startInvestigation,
    stopInvestigation,
    clearSession,
  } = useInvestigationStore();

  const handleStart = (e: React.FormEvent) => {
    e.preventDefault();
    if (target.trim()) {
      startInvestigation(target.trim(), category || undefined);
    }
  };

  const isRunning = session?.status === "running";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-zinc-100 flex items-center gap-3">
          <Radar className="w-6 h-6 text-sky-400" />
          Investigate
        </h1>
        <p className="text-sm text-zinc-500 mt-1">
          Launch a swarm of intelligence agents to gather data on a target
        </p>
      </div>

      {/* Start form */}
      <form onSubmit={handleStart} className="card space-y-4">
        <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
          New Investigation
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Target input */}
          <div className="md:col-span-2">
            <label className="block text-xs text-zinc-500 mb-1.5">
              Target (name, personnummer, or company)
            </label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
              <input
                type="text"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="e.g. Johan Andersson, 199001011234"
                className="w-full input-field pl-10"
                disabled={isRunning}
              />
            </div>
          </div>

          {/* Category select */}
          <div>
            <label className="block text-xs text-zinc-500 mb-1.5">
              Category focus
            </label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full input-field"
              disabled={isRunning}
            >
              {categoryOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-3">
          {!isRunning ? (
            <button
              type="submit"
              disabled={!target.trim() || isStarting}
              className="btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isStarting ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  Start Investigation
                </>
              )}
            </button>
          ) : (
            <button
              type="button"
              onClick={stopInvestigation}
              className="bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2"
            >
              <Square className="w-4 h-4" />
              Stop
            </button>
          )}

          {session && !isRunning && (
            <>
              <button
                type="button"
                onClick={() => navigate(`/profile/${session.session_id}`)}
                className="btn-primary flex items-center gap-2 text-sm"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                View Profile
              </button>
              <button
                type="button"
                onClick={clearSession}
                className="btn-secondary flex items-center gap-2 text-sm"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Clear
              </button>
            </>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2.5 text-sm text-red-400">
            {error}
          </div>
        )}
      </form>

      {/* Session info */}
      {session && (
        <div className="space-y-4">
          {/* Status bar */}
          <div className="card flex items-center justify-between">
            <div className="flex items-center gap-4">
              {/* Connection status */}
              <div className="flex items-center gap-2">
                {isConnected ? (
                  <>
                    <Wifi className="w-4 h-4 text-emerald-400" />
                    <span className="text-xs text-emerald-400">Live</span>
                  </>
                ) : (
                  <>
                    <WifiOff className="w-4 h-4 text-zinc-500" />
                    <span className="text-xs text-zinc-500">Disconnected</span>
                  </>
                )}
              </div>

              <div className="h-4 w-px bg-zinc-800" />

              {/* Target */}
              <div className="flex items-center gap-2">
                <User className="w-3.5 h-3.5 text-zinc-500" />
                <span className="text-sm text-zinc-300 font-medium">
                  {session.target}
                </span>
              </div>

              <div className="h-4 w-px bg-zinc-800" />

              {/* Status */}
              <span
                className={`text-xs px-2 py-0.5 rounded font-medium ${
                  isRunning
                    ? "bg-sky-500/15 text-sky-400"
                    : session.status === "completed"
                    ? "bg-emerald-500/15 text-emerald-400"
                    : "bg-red-500/15 text-red-400"
                }`}
              >
                {session.status}
              </span>
            </div>

            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1.5 text-xs text-zinc-400">
                <Database className="w-3 h-3" />
                <span className="font-mono">{session.total_facts}</span> facts
              </span>
              <span className="flex items-center gap-1.5 text-xs text-zinc-500">
                <Clock className="w-3 h-3" />
                {new Date(session.started_at).toLocaleTimeString("sv-SE")}
              </span>
            </div>
          </div>

          {/* Agent progress feed */}
          <div>
            <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-3">
              Agent Activity
            </h3>
            <SwarmFeed progress={progress} />
          </div>
        </div>
      )}
    </div>
  );
}
