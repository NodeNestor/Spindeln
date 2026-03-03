import { useNavigate } from "react-router-dom";
import { User, Building2, MapPin, Banknote } from "lucide-react";

interface PersonCardProps {
  id: string;
  name: string;
  age?: number;
  city?: string;
  income?: number;
  company_count?: number;
  photo_url?: string;
}

export default function PersonCard({
  id,
  name,
  age,
  city,
  income,
  company_count,
  photo_url,
}: PersonCardProps) {
  const navigate = useNavigate();

  return (
    <div
      onClick={() => navigate(`/profile/${id}`)}
      className="card-hover group animate-fade-in"
    >
      <div className="flex items-start gap-4">
        {/* Avatar */}
        <div className="w-12 h-12 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0 group-hover:border-sky-500/30 transition-colors">
          {photo_url ? (
            <img
              src={photo_url}
              alt={name}
              className="w-12 h-12 rounded-full object-cover"
            />
          ) : (
            <User className="w-6 h-6 text-zinc-500" />
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-zinc-100 truncate group-hover:text-sky-400 transition-colors">
            {name}
          </h3>
          {age && (
            <p className="text-xs text-zinc-500 mt-0.5">
              {age} years old
            </p>
          )}

          <div className="flex flex-wrap gap-3 mt-2.5">
            {city && (
              <span className="flex items-center gap-1 text-xs text-zinc-400">
                <MapPin className="w-3 h-3 text-amber-500" />
                {city}
              </span>
            )}
            {income !== undefined && (
              <span className="flex items-center gap-1 text-xs text-zinc-400">
                <Banknote className="w-3 h-3 text-emerald-500" />
                <span className="font-mono">
                  {income.toLocaleString("sv-SE")} kr
                </span>
              </span>
            )}
            {company_count !== undefined && company_count > 0 && (
              <span className="flex items-center gap-1 text-xs text-zinc-400">
                <Building2 className="w-3 h-3 text-emerald-500" />
                {company_count} {company_count === 1 ? "company" : "companies"}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
