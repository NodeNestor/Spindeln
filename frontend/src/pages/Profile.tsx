import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  User,
  MapPin,
  Phone,
  Mail,
  Calendar,
  CreditCard,
  Building2,
  Globe,
  Shield,
  Network,
  Loader2,
  AlertTriangle,
  ExternalLink,
  ArrowLeft,
  Clock,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useProfileStore } from "../stores/profile";
import CategoryRadar from "../components/CategoryRadar";
import ConnectionGraph from "../components/ConnectionGraph";
import SourceBadge from "../components/SourceBadge";
import FactCard from "../components/FactCard";

type TabId = "overview" | "financial" | "companies" | "social" | "breaches" | "connections";

const tabs: { id: TabId; label: string; icon: typeof User }[] = [
  { id: "overview", label: "Overview", icon: User },
  { id: "financial", label: "Financial", icon: CreditCard },
  { id: "companies", label: "Companies", icon: Building2 },
  { id: "social", label: "Social", icon: Globe },
  { id: "breaches", label: "Breaches", icon: Shield },
  { id: "connections", label: "Connections", icon: Network },
];

export default function Profile() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { profile, isLoading, error, fetchProfile, clearProfile } =
    useProfileStore();
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  useEffect(() => {
    if (id) {
      fetchProfile(id);
    }
    return () => clearProfile();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading) {
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

  if (!profile) {
    return (
      <div className="flex items-center justify-center h-96 text-zinc-500 text-sm">
        No profile data available
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Back + actions */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate(`/graph/${id}`)}
            className="btn-secondary text-xs flex items-center gap-1.5"
          >
            <Network className="w-3.5 h-3.5" />
            Full Graph
          </button>
          <button
            onClick={() => navigate(`/timeline/${id}`)}
            className="btn-secondary text-xs flex items-center gap-1.5"
          >
            <Clock className="w-3.5 h-3.5" />
            Timeline
          </button>
        </div>
      </div>

      {/* Profile header */}
      <div className="card flex items-start gap-5">
        {/* Avatar */}
        <div className="w-20 h-20 rounded-xl bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0">
          {profile.photo_url ? (
            <img
              src={profile.photo_url}
              alt={profile.name}
              className="w-20 h-20 rounded-xl object-cover"
            />
          ) : (
            <User className="w-10 h-10 text-zinc-600" />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-zinc-100">{profile.name}</h1>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
            {profile.age && (
              <span className="flex items-center gap-1.5 text-xs text-zinc-400">
                <Calendar className="w-3 h-3 text-zinc-500" />
                {profile.age} years
                {profile.date_of_birth && ` (${profile.date_of_birth})`}
              </span>
            )}
            {profile.personnummer && (
              <span className="text-xs font-mono text-zinc-500">
                {profile.personnummer}
              </span>
            )}
            {profile.address && (
              <span className="flex items-center gap-1.5 text-xs text-zinc-400">
                <MapPin className="w-3 h-3 text-amber-500" />
                {profile.address}
                {profile.postal_code && `, ${profile.postal_code}`}
                {profile.city && ` ${profile.city}`}
              </span>
            )}
            {profile.phone && (
              <span className="flex items-center gap-1.5 text-xs text-zinc-400">
                <Phone className="w-3 h-3 text-zinc-500" />
                <span className="font-mono">{profile.phone}</span>
              </span>
            )}
            {profile.email && (
              <span className="flex items-center gap-1.5 text-xs text-zinc-400">
                <Mail className="w-3 h-3 text-zinc-500" />
                {profile.email}
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 mt-3">
            <span className="text-xs text-zinc-500">
              {profile.total_facts} facts collected
            </span>
            <span className="text-xs text-zinc-600">|</span>
            <span className="text-xs text-zinc-500">
              Updated{" "}
              {new Date(profile.last_updated).toLocaleDateString("sv-SE")}
            </span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-zinc-800 flex gap-0 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === tab.id
                ? "border-sky-500 text-sky-400"
                : "border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-700"
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="animate-fade-in">
        {activeTab === "overview" && <OverviewTab />}
        {activeTab === "financial" && <FinancialTab />}
        {activeTab === "companies" && <CompaniesTab />}
        {activeTab === "social" && <SocialTab />}
        {activeTab === "breaches" && <BreachesTab />}
        {activeTab === "connections" && <ConnectionsTab />}
      </div>
    </div>
  );
}

function OverviewTab() {
  const profile = useProfileStore((s) => s.profile)!;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Facts */}
      <div className="lg:col-span-2 space-y-3">
        <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
          Recent Facts
        </h3>
        {profile.facts.length > 0 ? (
          profile.facts.slice(0, 10).map((fact) => (
            <FactCard
              key={fact.id}
              content={fact.content}
              source={fact.source}
              timestamp={fact.timestamp}
              confidence={fact.confidence}
              category={fact.category}
            />
          ))
        ) : (
          <p className="text-sm text-zinc-500 py-4">No facts collected yet</p>
        )}
      </div>

      {/* Category radar */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
          Data Completeness
        </h3>
        <div className="card">
          <CategoryRadar data={profile.category_completeness} />
        </div>

        {/* Quick stats */}
        <div className="card space-y-3">
          <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
            Summary
          </h4>
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-zinc-500">Companies</span>
              <span className="font-mono text-zinc-300">
                {profile.companies.length}
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-zinc-500">Connections</span>
              <span className="font-mono text-zinc-300">
                {profile.connections.length}
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-zinc-500">Social profiles</span>
              <span className="font-mono text-zinc-300">
                {profile.social_profiles.length}
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-zinc-500">Breaches</span>
              <span className="font-mono text-zinc-300">
                {profile.breaches.length}
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-zinc-500">Payment remarks</span>
              <span
                className={`font-mono ${
                  profile.financial.payment_remarks
                    ? "text-red-400"
                    : "text-emerald-400"
                }`}
              >
                {profile.financial.payment_remarks ? "Yes" : "No"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function FinancialTab() {
  const profile = useProfileStore((s) => s.profile)!;
  const { financial } = profile;

  const incomeData = (financial.income_history || []).map((item) => ({
    year: item.year.toString(),
    income: item.amount,
  }));

  return (
    <div className="space-y-6">
      {/* Key financial metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card">
          <p className="text-xs text-zinc-500 uppercase tracking-wider">
            Annual Income
          </p>
          <p className="stat-number text-emerald-400 mt-1">
            {financial.income
              ? `${financial.income.toLocaleString("sv-SE")} kr`
              : "N/A"}
          </p>
        </div>
        <div className="card">
          <p className="text-xs text-zinc-500 uppercase tracking-wider">
            Tax Paid
          </p>
          <p className="stat-number text-amber-400 mt-1">
            {financial.tax
              ? `${financial.tax.toLocaleString("sv-SE")} kr`
              : "N/A"}
          </p>
        </div>
        <div className="card">
          <p className="text-xs text-zinc-500 uppercase tracking-wider">
            Payment Remarks
          </p>
          <p
            className={`stat-number mt-1 ${
              financial.payment_remarks ? "text-red-400" : "text-emerald-400"
            }`}
          >
            {financial.payment_remarks
              ? `${financial.remark_count || "Yes"}`
              : "None"}
          </p>
        </div>
      </div>

      {/* Income chart */}
      {incomeData.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-zinc-300 mb-4">
            Income History
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={incomeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis
                dataKey="year"
                tick={{ fill: "#a1a1aa", fontSize: 12 }}
                axisLine={{ stroke: "#3f3f46" }}
              />
              <YAxis
                tick={{ fill: "#a1a1aa", fontSize: 11 }}
                axisLine={{ stroke: "#3f3f46" }}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#18181b",
                  border: "1px solid #3f3f46",
                  borderRadius: "8px",
                  color: "#e4e4e7",
                  fontSize: "12px",
                }}
                formatter={(value: number) => [
                  `${value.toLocaleString("sv-SE")} kr`,
                  "Income",
                ]}
              />
              <Bar
                dataKey="income"
                fill="#10b981"
                radius={[4, 4, 0, 0]}
                maxBarSize={60}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Financial facts */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
          Financial Records
        </h3>
        {profile.facts
          .filter((f) => f.category === "financial")
          .map((fact) => (
            <FactCard
              key={fact.id}
              content={fact.content}
              source={fact.source}
              timestamp={fact.timestamp}
              confidence={fact.confidence}
              category={fact.category}
            />
          ))}
      </div>
    </div>
  );
}

function CompaniesTab() {
  const profile = useProfileStore((s) => s.profile)!;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
        Company Roles ({profile.companies.length})
      </h3>

      {profile.companies.length === 0 ? (
        <p className="text-sm text-zinc-500 py-4">No company roles found</p>
      ) : (
        <div className="card overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800">
                <th className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wider font-medium">
                  Company
                </th>
                <th className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wider font-medium">
                  Org. Number
                </th>
                <th className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wider font-medium">
                  Role
                </th>
                <th className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wider font-medium">
                  Since
                </th>
              </tr>
            </thead>
            <tbody>
              {profile.companies.map((company, idx) => (
                <tr
                  key={idx}
                  className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/30 transition-colors"
                >
                  <td className="px-4 py-3 text-zinc-200 font-medium">
                    {company.company_name}
                  </td>
                  <td className="px-4 py-3 font-mono text-zinc-400 text-xs">
                    {company.org_number}
                  </td>
                  <td className="px-4 py-3 text-zinc-300">
                    {company.role}
                  </td>
                  <td className="px-4 py-3 text-zinc-500 font-mono text-xs">
                    {company.since || "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SocialTab() {
  const profile = useProfileStore((s) => s.profile)!;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
        Social Media Profiles ({profile.social_profiles.length})
      </h3>

      {profile.social_profiles.length === 0 ? (
        <p className="text-sm text-zinc-500 py-4">No social profiles found</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {profile.social_profiles.map((sp, idx) => (
            <div key={idx} className="card flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-zinc-800 flex items-center justify-center">
                  <Globe className="w-4 h-4 text-blue-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-zinc-200">
                    {sp.platform}
                  </p>
                  <p className="text-xs text-zinc-400">@{sp.username}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {sp.verified && (
                  <span className="text-xs bg-emerald-500/15 text-emerald-400 px-2 py-0.5 rounded">
                    Verified
                  </span>
                )}
                {sp.url && (
                  <a
                    href={sp.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-zinc-500 hover:text-zinc-300 transition-colors"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Social facts */}
      <div className="space-y-3 mt-6">
        <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
          Social Records
        </h3>
        {profile.facts
          .filter((f) => f.category === "social")
          .map((fact) => (
            <FactCard
              key={fact.id}
              content={fact.content}
              source={fact.source}
              timestamp={fact.timestamp}
              confidence={fact.confidence}
              category={fact.category}
            />
          ))}
      </div>
    </div>
  );
}

function BreachesTab() {
  const profile = useProfileStore((s) => s.profile)!;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
        Data Breaches ({profile.breaches.length})
      </h3>

      {profile.breaches.length === 0 ? (
        <div className="card flex items-center gap-3 py-6 justify-center">
          <Shield className="w-5 h-5 text-emerald-400" />
          <p className="text-sm text-emerald-400">
            No known breaches found
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {profile.breaches.map((breach, idx) => (
            <div
              key={idx}
              className="card border-l-2 border-l-red-500 animate-fade-in"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h4 className="text-sm font-semibold text-red-400">
                    {breach.breach_name}
                  </h4>
                  <p className="text-xs text-zinc-500 font-mono mt-0.5">
                    {breach.date
                      ? new Date(breach.date).toLocaleDateString("sv-SE")
                      : "Unknown date"}
                  </p>
                </div>
                <SourceBadge source={breach.source} />
              </div>

              {breach.exposed_data.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {breach.exposed_data.map((field) => (
                    <span
                      key={field}
                      className="text-xs bg-red-500/10 text-red-300 px-2 py-0.5 rounded"
                    >
                      {field}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ConnectionsTab() {
  const profile = useProfileStore((s) => s.profile)!;

  const nodes = [
    {
      id: profile.id,
      name: profile.name,
      type: "person" as const,
      val: 10,
    },
    ...profile.connections.map((c) => ({
      id: c.id,
      name: c.name,
      type: c.type,
      val: 6,
    })),
  ];

  const links = profile.connections.map((c) => ({
    source: profile.id,
    target: c.id,
    label: c.relationship,
  }));

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
        Network ({profile.connections.length} connections)
      </h3>

      {profile.connections.length === 0 ? (
        <p className="text-sm text-zinc-500 py-4">No connections found</p>
      ) : (
        <>
          <div className="card p-0 overflow-hidden">
            <ConnectionGraph nodes={nodes} links={links} height={500} />
          </div>

          {/* Connection list */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {profile.connections.map((conn) => (
              <div key={conn.id} className="card-hover flex items-center gap-3">
                <div
                  className={`w-2 h-2 rounded-full ${
                    conn.type === "person"
                      ? "bg-sky-500"
                      : conn.type === "company"
                      ? "bg-emerald-500"
                      : "bg-amber-500"
                  }`}
                />
                <div className="min-w-0">
                  <p className="text-sm text-zinc-200 truncate">{conn.name}</p>
                  <p className="text-xs text-zinc-500 capitalize">
                    {conn.relationship} ({conn.type})
                  </p>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
