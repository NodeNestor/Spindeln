import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { Search as SearchIcon, Filter, Loader2, X } from "lucide-react";
import PersonCard from "../components/PersonCard";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8083";

interface SearchResult {
  id: string;
  name: string;
  age?: number;
  city?: string;
  income?: number;
  company_count?: number;
  photo_url?: string;
}

const categories = [
  { value: "", label: "All categories" },
  { value: "personal", label: "Personal" },
  { value: "financial", label: "Financial" },
  { value: "companies", label: "Companies" },
  { value: "social", label: "Social" },
  { value: "breach", label: "Breaches" },
];

export default function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [category, setCategory] = useState(searchParams.get("cat") || "");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [total, setTotal] = useState(0);

  const performSearch = useCallback(
    async (q: string, cat: string) => {
      if (!q.trim()) return;

      setIsLoading(true);
      setHasSearched(true);

      try {
        const params = new URLSearchParams({ q: q.trim() });
        if (cat) params.set("category", cat);

        const res = await fetch(`${API_URL}/api/search?${params}`);
        if (res.ok) {
          const data = await res.json();
          setResults(data.results || data || []);
          setTotal(data.total || (data.results || data || []).length);
        } else {
          setResults([]);
          setTotal(0);
        }
      } catch {
        setResults([]);
        setTotal(0);
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  // Search on initial load if query param present
  useEffect(() => {
    const q = searchParams.get("q");
    const cat = searchParams.get("cat");
    if (q) {
      setQuery(q);
      if (cat) setCategory(cat);
      performSearch(q, cat || "");
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const params: Record<string, string> = {};
    if (query.trim()) params.q = query.trim();
    if (category) params.cat = category;
    setSearchParams(params);
    performSearch(query, category);
  };

  const clearSearch = () => {
    setQuery("");
    setCategory("");
    setResults([]);
    setHasSearched(false);
    setSearchParams({});
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">Search</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Search across all person records and data sources
        </p>
      </div>

      {/* Search form */}
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="flex gap-3">
          <div className="relative flex-1">
            <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-500" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Name, personnummer, address, company..."
              className="w-full input-field pl-12 pr-10 py-3"
              autoFocus
            />
            {query && (
              <button
                type="button"
                onClick={clearSearch}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Category filter */}
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="input-field pl-9 pr-8 py-3 appearance-none bg-zinc-900 min-w-[160px]"
            >
              {categories.map((cat) => (
                <option key={cat.value} value={cat.value}>
                  {cat.label}
                </option>
              ))}
            </select>
          </div>

          <button type="submit" className="btn-primary px-6" disabled={isLoading}>
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              "Search"
            )}
          </button>
        </div>
      </form>

      {/* Results */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div
              key={i}
              className="card h-24 animate-pulse bg-zinc-900/50"
            />
          ))}
        </div>
      ) : hasSearched ? (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-zinc-500">
              {total === 0
                ? "No results found"
                : `${total} result${total !== 1 ? "s" : ""} found`}
            </p>
          </div>

          {results.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {results.map((person) => (
                <PersonCard
                  key={person.id}
                  id={person.id}
                  name={person.name}
                  age={person.age}
                  city={person.city}
                  income={person.income}
                  company_count={person.company_count}
                  photo_url={person.photo_url}
                />
              ))}
            </div>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center justify-center py-16 text-zinc-500">
          <SearchIcon className="w-12 h-12 mb-4 text-zinc-700" />
          <p className="text-sm">Enter a search query to find persons</p>
          <p className="text-xs text-zinc-600 mt-1">
            Try a name, personnummer, address, or company name
          </p>
        </div>
      )}
    </div>
  );
}
