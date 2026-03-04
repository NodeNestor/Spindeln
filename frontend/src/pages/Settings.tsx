import { useState, useEffect, useCallback } from "react";
import {
  Save,
  CheckCircle,
  XCircle,
  Loader2,
  Server,
  Brain,
  Sparkles,
  SlidersHorizontal,
} from "lucide-react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8083";

type TestStatus = "idle" | "testing" | "ok" | "fail";

interface FieldState {
  [key: string]: string | number;
}

export default function Settings() {
  const [config, setConfig] = useState<FieldState>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testStatus, setTestStatus] = useState<Record<string, TestStatus>>({});

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/config`);
      if (res.ok) setConfig(await res.json());
    } catch {
      // API may not be running
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleChange = (key: string, value: string | number) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (res.ok) {
        const updated = await res.json();
        setConfig(updated);
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      }
    } catch {
      // handle error
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (key: string) => {
    const url = config[key] as string;
    if (!url) return;
    setTestStatus((prev) => ({ ...prev, [key]: "testing" }));
    try {
      const res = await fetch(`${API_URL}/api/test-endpoint`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      setTestStatus((prev) => ({ ...prev, [key]: data.ok ? "ok" : "fail" }));
    } catch {
      setTestStatus((prev) => ({ ...prev, [key]: "fail" }));
    }
    setTimeout(
      () => setTestStatus((prev) => ({ ...prev, [key]: "idle" })),
      5000,
    );
  };

  const TestButton = ({ field }: { field: string }) => {
    const status = testStatus[field] || "idle";
    return (
      <button
        type="button"
        onClick={() => handleTest(field)}
        disabled={status === "testing"}
        className="shrink-0 px-3 py-2 rounded-lg text-xs font-medium transition-colors border border-zinc-700 hover:border-zinc-600 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 disabled:opacity-50"
      >
        {status === "testing" ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : status === "ok" ? (
          <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
        ) : status === "fail" ? (
          <XCircle className="w-3.5 h-3.5 text-red-400" />
        ) : (
          "Test"
        )}
      </button>
    );
  };

  const Field = ({
    label,
    field,
    type = "text",
    placeholder = "",
    testable = false,
    help = "",
  }: {
    label: string;
    field: string;
    type?: string;
    placeholder?: string;
    testable?: boolean;
    help?: string;
  }) => (
    <div className="space-y-1.5">
      <label className="block text-xs font-medium text-zinc-400">
        {label}
      </label>
      <div className="flex gap-2">
        <input
          type={type}
          value={config[field] ?? ""}
          onChange={(e) =>
            handleChange(
              field,
              type === "number" ? Number(e.target.value) : e.target.value,
            )
          }
          placeholder={placeholder}
          className="input-field flex-1 text-sm py-2"
        />
        {testable && <TestButton field={field} />}
      </div>
      {help && <p className="text-xs text-zinc-600">{help}</p>}
    </div>
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-zinc-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header + Save */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">Settings</h1>
          <p className="text-sm text-zinc-500 mt-1">
            Configure service endpoints and LLM providers
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-primary flex items-center gap-2"
        >
          {saving ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : saved ? (
            <CheckCircle className="w-4 h-4" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          {saved ? "Saved" : "Save"}
        </button>
      </div>

      {/* Services */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <Server className="w-4 h-4 text-sky-400" />
          <h2 className="text-sm font-semibold text-zinc-200">Services</h2>
        </div>
        <Field
          label="HiveMindDB URL"
          field="hiveminddb_url"
          placeholder="http://hiveminddb:8100"
          testable
        />
        <Field
          label="SearXNG URL"
          field="searxng_url"
          placeholder="http://searxng:8080"
          testable
        />
        <Field
          label="Crawl4AI URL"
          field="crawl4ai_url"
          placeholder="http://crawl4ai:11235"
          testable
        />
      </section>

      {/* Bulk Extraction Model */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <Brain className="w-4 h-4 text-amber-400" />
          <h2 className="text-sm font-semibold text-zinc-200">
            Extraction Model (Bulk)
          </h2>
        </div>
        <Field
          label="API URL"
          field="bulk_api_url"
          placeholder="http://vllm:8000/v1"
          testable
        />
        <Field
          label="Model Name"
          field="bulk_model"
          placeholder="Qwen/Qwen3-8B-AWQ"
        />
        <Field
          label="API Key"
          field="bulk_api_key"
          type="password"
          placeholder="Leave empty if not required"
        />
        <Field
          label="Max Tokens"
          field="bulk_max_tokens"
          type="number"
          placeholder="4096"
        />
      </section>

      {/* Synthesis Model */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <Sparkles className="w-4 h-4 text-violet-400" />
          <h2 className="text-sm font-semibold text-zinc-200">
            Synthesis Model (Report Writer)
          </h2>
        </div>
        <p className="text-xs text-zinc-500 -mt-2">
          Can be a different provider — e.g., use local vLLM for extraction but
          OpenAI/Anthropic for report synthesis.
        </p>
        <Field
          label="API URL"
          field="synthesis_api_url"
          placeholder="https://api.openai.com/v1"
          testable
        />
        <Field
          label="Model Name"
          field="synthesis_model"
          placeholder="gpt-4o / claude-sonnet / Qwen3.5-9B"
        />
        <Field
          label="API Key"
          field="synthesis_api_key"
          type="password"
          placeholder="sk-... or leave empty for local models"
        />
        <Field
          label="Max Tokens"
          field="synthesis_max_tokens"
          type="number"
          placeholder="16384"
        />
      </section>

      {/* Investigation Defaults */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <SlidersHorizontal className="w-4 h-4 text-emerald-400" />
          <h2 className="text-sm font-semibold text-zinc-200">
            Investigation Defaults
          </h2>
        </div>
        <Field
          label="Scrape Concurrency"
          field="scrape_concurrency"
          type="number"
          placeholder="5"
          help="Number of parallel scrape requests (1-20)"
        />
      </section>
    </div>
  );
}
