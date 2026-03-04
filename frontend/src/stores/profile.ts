import { create } from "zustand";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8083";

export interface Fact {
  id: string;
  content: string;
  category: string;
  source: string;
  confidence: number;
  timestamp: string;
  quality_score?: number;
  source_url?: string;
  source_title?: string;
  metadata?: Record<string, any>;
}

export interface Connection {
  id: string;
  name: string;
  type: "person" | "company" | "address" | "phone" | "email";
  relationship: string;
}

export interface CompanyRole {
  company_name: string;
  org_number: string;
  role: string;
  since?: string;
}

export interface SocialProfile {
  platform: string;
  username: string;
  url: string;
  verified: boolean;
}

export interface BreachRecord {
  breach_name: string;
  date: string;
  exposed_data: string[];
  source: string;
}

export interface FinancialData {
  income?: number;
  tax?: number;
  payment_remarks: boolean;
  remark_count?: number;
  income_history?: { year: number; amount: number }[];
}

export interface ReportSection {
  heading: string;
  body: string;
  confidence: number;
  citations?: string[];
}

export interface ReportData {
  // New DeepResearch-style fields
  title?: string;
  summary?: string;
  sections?: ReportSection[];
  key_findings?: string[];
  confidence_overall?: number;
  gaps?: string[];
  // Legacy fields (backward compat)
  narrative?: string;
  key_facts?: string[];
  risk_assessment?: string;
  data_quality?: "high" | "medium" | "low" | string;
  connections_summary?: string;
}

export interface PersonProfile {
  id: string;
  name: string;
  age?: number;
  date_of_birth?: string;
  personnummer?: string;
  address?: string;
  city?: string;
  postal_code?: string;
  phone?: string;
  email?: string;
  photo_url?: string;

  facts: Fact[];
  connections: Connection[];
  companies: CompanyRole[];
  social_profiles: SocialProfile[];
  breaches: BreachRecord[];
  financial: FinancialData;
  report?: ReportData | null;

  category_completeness: Record<string, number>;
  total_facts: number;
  last_updated: string;
}

interface ProfileStore {
  profile: PersonProfile | null;
  isLoading: boolean;
  error: string | null;

  fetchProfile: (id: string) => Promise<void>;
  clearProfile: () => void;
}

export const useProfileStore = create<ProfileStore>((set) => ({
  profile: null,
  isLoading: false,
  error: null,

  fetchProfile: async (id: string) => {
    set({ isLoading: true, error: null });

    try {
      const res = await fetch(`${API_URL}/api/persons/${id}`);
      if (!res.ok) {
        throw new Error(`Failed to fetch profile: HTTP ${res.status}`);
      }

      const data = await res.json();

      const profile: PersonProfile = {
        id: data.id || id,
        name: data.name || "Unknown",
        age: data.age,
        date_of_birth: data.date_of_birth,
        personnummer: data.personnummer,
        address: data.address,
        city: data.city,
        postal_code: data.postal_code,
        phone: data.phone,
        email: data.email,
        photo_url: data.photo_url,

        facts: data.facts || [],
        connections: data.connections || [],
        companies: data.companies || [],
        social_profiles: data.social_profiles || [],
        breaches: data.breaches || [],
        financial: data.financial || { payment_remarks: false },

        report: data.report || null,
        category_completeness: data.category_completeness || {},
        total_facts: data.total_facts || (data.facts || []).length,
        last_updated: data.last_updated || new Date().toISOString(),
      };

      set({ profile, isLoading: false });
    } catch (err: any) {
      set({
        isLoading: false,
        error: err.message || "Failed to fetch profile",
      });
    }
  },

  clearProfile: () => {
    set({ profile: null, error: null });
  },
}));
