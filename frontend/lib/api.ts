/**
 * Every call to the HeatGov AI backend goes through this file.
 *
 * The shapes below mirror the FastAPI responses exactly. If the backend
 * changes, TypeScript breaks here first instead of failing silently in the UI
 * during a demo.
 */

/**
 * Where the backend lives.
 *
 * On Vercel this is set to the Render URL; with nothing set it falls back to
 * the local uvicorn, so `npm run dev` needs no configuration at all.
 *
 * Next.js inlines `process.env.NEXT_PUBLIC_*` at BUILD time, not at run time.
 * Changing this variable in the Vercel dashboard therefore has no effect until
 * the project is redeployed - see docs/DEPLOYMENT.md.
 *
 * `NEXT_PUBLIC_API_BASE` is the name this project used first and is still
 * honoured so existing `.env.local` files keep working.
 */
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "http://localhost:8000";

/** @deprecated Use {@link API_URL}. Kept so older imports do not break. */
export const API_BASE = API_URL;

/* ----------------------------------------------------------------- layers */

export type LayerId =
  | "tcm_peak_15h"
  | "tcm_peak_22h"
  | "exceedance"
  | "persistence";

export interface LayerOption {
  id: LayerId;
  label: string;
  hint: string;
  starred?: boolean;
}

export const LAYERS: LayerOption[] = [
  { id: "tcm_peak_22h", label: "Night 22:00", hint: "Temperature at 22:00 local", starred: true },
  { id: "tcm_peak_15h", label: "Day 15:00", hint: "Temperature at 15:00 local" },
  { id: "exceedance", label: "Exceedance", hint: "Hours above 30 C in July 2025" },
  { id: "persistence", label: "Persistence", hint: "Longest unbroken stretch above 30 C" },
];

/* ------------------------------------------------------------- responses */

export interface HeatmapStats {
  min: number;
  p5: number;
  mean: number;
  p95: number;
  max: number;
}

export interface HeatmapMetadata {
  analytic_type: string;
  value_column: string;
  unit: string;
  description: string;
  tiles: number;
  stats: HeatmapStats;
}

export interface HeatmapResponse {
  type: "FeatureCollection";
  features: GeoJSON.Feature[];
  metadata: HeatmapMetadata;
}

export interface Zone {
  tract_fips: string;
  name: string;
  risk_score: number;
  physical_score: number | null;
  night_temp_c: number;
  impervious_surface_pct: number;
  median_income_usd: number;
  lat: number;
  lon: number;
}

export interface ZonesResponse {
  zones: Zone[];
  count: number;
  total_tracts_analyzed: number;
}

export interface ShapDriver {
  feature: string;
  label: string;
  value: number;
  unit: string;
  impact_points: number;
  explanation: string;
}

export interface PredictResponse {
  tract_fips: string;
  name: string;
  risk_score_b: number;
  risk_score_a: number;
  official_calenviroscreen_score: number;
  top_shap_features: ShapDriver[];
  note: string;
}

export interface PlanItem {
  tract_fips: string;
  name: string;
  intervention: string;
  detail: string;
  cost_usd: number;
  risk_score: number;
  expected_reduction_c: number;
}

export interface OptimizeResponse {
  plan: PlanItem[];
  total_cost_usd: number;
  budget_usd: number;
  remaining_usd: number;
  zones_funded: number;
  zones_considered: number;
  coverage_score: number;
  mean_expected_reduction_c: number;
  reduction_note: string;
  mean_risk_of_funded_zones: number;
  cost_note: string;
  canopy_data_available: boolean;
  data_caveat?: string;
}

export interface ChatResponse {
  reply: string;
  tool_calls: { tool: string; args: Record<string, unknown> }[];
  rounds: number;
  model: string;
  session_id: string | null;
}

export interface HealthResponse {
  status: string;
  model_a_r2: number | null;
  model_b_r2: number | null;
  model_loaded: boolean;
  study_area: string;
  tracts: number;
  gemini_model: string;
  gemini_configured: boolean;
}

/* -------------------------------------------------------------- requests */

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    // FastAPI puts the reason in `detail`; surface it instead of "500".
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* body was not JSON */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const getHealth = () => request<HealthResponse>("/api/health");

export const getHeatmap = (layer: LayerId) =>
  request<HeatmapResponse>(`/api/heatmap/${layer}`);

export const getRankedZones = (topN = 10) =>
  request<ZonesResponse>(`/api/zones/ranked?top_n=${topN}`);

export const predictTract = (tractFips: string) =>
  request<PredictResponse>("/api/predict", {
    method: "POST",
    body: JSON.stringify({ tract_fips: tractFips }),
  });

export const optimizeBudget = (budgetUsd: number, topN = 10) =>
  request<OptimizeResponse>("/api/optimize", {
    method: "POST",
    body: JSON.stringify({ budget_usd: budgetUsd, top_n: topN }),
  });

export const sendChat = (message: string, sessionId: string) =>
  request<ChatResponse>("/api/agent/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId }),
  });

/* --------------------------------------------------------------- helpers */

export const usd = (value: number) =>
  value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });

export const INTERVENTION_LABELS: Record<string, string> = {
  cool_roof: "Cool Roofs",
  trees: "Tree Planting",
  shade: "Shade Structures",
};
