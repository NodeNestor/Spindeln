import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Loader2, AlertTriangle, Filter } from "lucide-react";
import TimelineView, { TimelineEvent } from "../components/TimelineView";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8082";

const categoryFilters = [
  { value: "", label: "All", color: "bg-zinc-500" },
  { value: "financial", label: "Financial", color: "bg-emerald-500" },
  { value: "social", label: "Social", color: "bg-blue-500" },
  { value: "breach", label: "Breach", color: "bg-red-500" },
  { value: "news", label: "News", color: "bg-purple-500" },
  { value: "personal", label: "Personal", color: "bg-sky-500" },
  { value: "company", label: "Company", color: "bg-emerald-400" },
];

export default function Timeline() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [personName, setPersonName] = useState("");

  useEffect(() => {
    const fetchTimeline = async () => {
      try {
        const res = await fetch(`${API_URL}/api/persons/${id}/timeline`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();
        setEvents(data.events || data || []);
        setPersonName(data.person_name || "");
      } catch (err: any) {
        setError(err.message || "Failed to load timeline");
      } finally {
        setLoading(false);
      }
    };

    if (id) fetchTimeline();
  }, [id]);

  const filteredEvents = filter
    ? events.filter((e) => e.category === filter)
    : events;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="w-8 h-8 animate-spin text-sky-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-zinc-400">
        <AlertTriangle className="w-10 h-10 text-red-400 mb-3" />
        <p className="text-sm">{error}</p>
        <button
          onClick={() => navigate(-1)}
          className="btn-secondary mt-4 text-sm"
        >
          Go back
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors mb-2"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </button>
          <h1 className="text-2xl font-bold text-zinc-100">
            Timeline{personName ? `: ${personName}` : ""}
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            {filteredEvents.length} event{filteredEvents.length !== 1 ? "s" : ""}{" "}
            {filter ? `in ${filter}` : "total"}
          </p>
        </div>
      </div>

      {/* Category filter */}
      <div className="flex items-center gap-2 flex-wrap">
        <Filter className="w-4 h-4 text-zinc-500" />
        {categoryFilters.map((cat) => (
          <button
            key={cat.value}
            onClick={() => setFilter(cat.value)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              filter === cat.value
                ? "bg-zinc-700 text-zinc-100 border border-zinc-600"
                : "bg-zinc-900 text-zinc-400 border border-zinc-800 hover:border-zinc-700 hover:text-zinc-300"
            }`}
          >
            <div className={`w-2 h-2 rounded-full ${cat.color}`} />
            {cat.label}
          </button>
        ))}
      </div>

      {/* Timeline */}
      <div className="max-w-3xl">
        <TimelineView events={filteredEvents} />
      </div>
    </div>
  );
}
