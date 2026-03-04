import { create } from "zustand";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8083";
const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8083/ws";

export interface AgentProgress {
  id: string;
  agent_name: string;
  status: "running" | "completed" | "failed" | "queued";
  message: string;
  facts_found: number;
  timestamp: string;
}

export interface InvestigationSession {
  session_id: string;
  target: string;
  status: "running" | "completed" | "failed";
  started_at: string;
  progress: AgentProgress[];
  total_facts: number;
}

interface InvestigationStore {
  session: InvestigationSession | null;
  progress: AgentProgress[];
  isConnected: boolean;
  isStarting: boolean;
  ws: WebSocket | null;
  error: string | null;

  startInvestigation: (
    target: string,
    category?: string
  ) => Promise<void>;
  stopInvestigation: () => void;
  connectWebSocket: (sessionId: string) => void;
  disconnectWebSocket: () => void;
  clearSession: () => void;
}

export const useInvestigationStore = create<InvestigationStore>((set, get) => ({
  session: null,
  progress: [],
  isConnected: false,
  isStarting: false,
  ws: null,
  error: null,

  startInvestigation: async (target: string, category?: string) => {
    set({ isStarting: true, error: null, progress: [] });

    try {
      const body: Record<string, string> = { query: target };
      if (category) body.category = category;

      const res = await fetch(`${API_URL}/api/investigate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();

      const session: InvestigationSession = {
        session_id: data.session_id,
        target,
        status: "running",
        started_at: new Date().toISOString(),
        progress: [],
        total_facts: 0,
      };

      set({ session, isStarting: false });

      // Connect WebSocket for live updates
      get().connectWebSocket(data.session_id);
    } catch (err: any) {
      set({
        isStarting: false,
        error: err.message || "Failed to start investigation",
      });
    }
  },

  stopInvestigation: () => {
    const { session } = get();
    if (session) {
      fetch(`${API_URL}/api/investigate/${session.session_id}/stop`, {
        method: "POST",
      }).catch(() => {});
    }
    get().disconnectWebSocket();
    set((state) => ({
      session: state.session
        ? { ...state.session, status: "completed" }
        : null,
    }));
  },

  connectWebSocket: (sessionId: string) => {
    get().disconnectWebSocket();

    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      set({ isConnected: true });
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as AgentProgress;
        set((state) => {
          const newProgress = [...state.progress, data];
          const totalFacts = newProgress.reduce(
            (sum, p) => sum + (p.facts_found || 0),
            0
          );
          return {
            progress: newProgress,
            session: state.session
              ? {
                  ...state.session,
                  progress: newProgress,
                  total_facts: totalFacts,
                }
              : null,
          };
        });
      } catch {
        // Ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      set({ isConnected: false, ws: null });
    };

    ws.onerror = () => {
      set({ error: "WebSocket connection lost", isConnected: false });
    };

    set({ ws });
  },

  disconnectWebSocket: () => {
    const { ws } = get();
    if (ws) {
      ws.close();
      set({ ws: null, isConnected: false });
    }
  },

  clearSession: () => {
    get().disconnectWebSocket();
    set({ session: null, progress: [], error: null });
  },
}));
