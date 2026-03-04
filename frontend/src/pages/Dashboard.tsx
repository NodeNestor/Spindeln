import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  Users,
  Radar,
  Bot,
  ArrowRight,
  Clock,
  TrendingUp,
} from "lucide-react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8083";

interface Stats {
  total_persons: number;
  total_investigations: number;
  active_agents: number;
}

interface RecentInvestigation {
  id: string;
  target: string;
  status: string;
  started_at: string;
  total_facts: number;
  person_id?: string;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState("");
  const [stats, setStats] = useState<Stats>({
    total_persons: 0,
    total_investigations: 0,
    active_agents: 0,
  });
  const [recent, setRecent] = useState<RecentInvestigation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statsRes, recentRes] = await Promise.allSettled([
          fetch(`${API_URL}/api/stats`),
          fetch(`${API_URL}/api/investigations/recent`),
        ]);

        if (statsRes.status === "fulfilled" && statsRes.value.ok) {
          setStats(await statsRes.value.json());
        }
        if (recentRes.status === "fulfilled" && recentRes.value.ok) {
          setRecent(await recentRes.value.json());
        }
      } catch {
        // API may not be running yet
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  const statCards = [
    {
      label: "Total Persons",
      value: stats.total_persons,
      icon: Users,
      color: "text-sky-400",
      bgColor: "bg-sky-500/10",
    },
    {
      label: "Investigations",
      value: stats.total_investigations,
      icon: Radar,
      color: "text-emerald-400",
      bgColor: "bg-emerald-500/10",
    },
    {
      label: "Active Agents",
      value: stats.active_agents,
      icon: Bot,
      color: "text-amber-400",
      bgColor: "bg-amber-500/10",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">Dashboard</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Intelligence overview and quick actions
        </p>
      </div>

      {/* Quick search */}
      <form onSubmit={handleSearch} className="relative max-w-2xl">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-500" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search by name, personnummer, or company..."
          className="w-full input-field pl-12 pr-24 py-3 text-base"
          autoFocus
        />
        <button
          type="submit"
          className="absolute right-2 top-1/2 -translate-y-1/2 btn-primary py-1.5 text-sm"
        >
          Search
        </button>
      </form>

      {/* Stats cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {statCards.map((stat) => (
          <div key={stat.label} className="card animate-fade-in">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-zinc-500 uppercase tracking-wider font-medium">
                  {stat.label}
                </p>
                <p className="stat-number mt-1">
                  {loading ? (
                    <span className="inline-block w-12 h-7 bg-zinc-800 rounded animate-pulse" />
                  ) : (
                    stat.value.toLocaleString("sv-SE")
                  )}
                </p>
              </div>
              <div
                className={`w-10 h-10 rounded-lg ${stat.bgColor} flex items-center justify-center`}
              >
                <stat.icon className={`w-5 h-5 ${stat.color}`} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <button
          onClick={() => navigate("/investigate")}
          className="card-hover flex items-center gap-4 text-left"
        >
          <div className="w-10 h-10 rounded-lg bg-sky-500/10 flex items-center justify-center shrink-0">
            <Radar className="w-5 h-5 text-sky-400" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-zinc-200">
              New Investigation
            </h3>
            <p className="text-xs text-zinc-500 mt-0.5">
              Launch a swarm of agents to gather intelligence
            </p>
          </div>
          <ArrowRight className="w-4 h-4 text-zinc-600" />
        </button>

        <button
          onClick={() => navigate("/search")}
          className="card-hover flex items-center gap-4 text-left"
        >
          <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center shrink-0">
            <Search className="w-5 h-5 text-emerald-400" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-zinc-200">
              Advanced Search
            </h3>
            <p className="text-xs text-zinc-500 mt-0.5">
              Search across all person records and data sources
            </p>
          </div>
          <ArrowRight className="w-4 h-4 text-zinc-600" />
        </button>
      </div>

      {/* Recent investigations */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-zinc-200 flex items-center gap-2">
            <Clock className="w-4 h-4 text-zinc-500" />
            Recent Investigations
          </h2>
          {recent.length > 0 && (
            <button
              onClick={() => navigate("/investigate")}
              className="text-xs text-sky-400 hover:text-sky-300 transition-colors"
            >
              View all
            </button>
          )}
        </div>

        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="card h-16 animate-pulse bg-zinc-900/50"
              />
            ))}
          </div>
        ) : recent.length === 0 ? (
          <div className="card flex items-center justify-center py-8 text-zinc-500 text-sm">
            No investigations yet. Start one to see results here.
          </div>
        ) : (
          <div className="space-y-2">
            {recent.map((inv) => (
              <div
                key={inv.id}
                className="card-hover flex items-center justify-between"
                onClick={() => navigate(`/profile/${inv.person_id || inv.id}`)}
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      inv.status === "running"
                        ? "bg-sky-400 animate-pulse-slow"
                        : inv.status === "completed"
                        ? "bg-emerald-400"
                        : "bg-red-400"
                    }`}
                  />
                  <div>
                    <p className="text-sm font-medium text-zinc-200">
                      {inv.target}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {inv.started_at
                        ? new Date(inv.started_at).toLocaleString("sv-SE")
                        : ""}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <span className="flex items-center gap-1 text-xs font-mono text-zinc-400">
                    <TrendingUp className="w-3 h-3" />
                    {inv.total_facts} facts
                  </span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded font-medium ${
                      inv.status === "running"
                        ? "bg-sky-500/15 text-sky-400"
                        : inv.status === "completed"
                        ? "bg-emerald-500/15 text-emerald-400"
                        : "bg-red-500/15 text-red-400"
                    }`}
                  >
                    {inv.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
