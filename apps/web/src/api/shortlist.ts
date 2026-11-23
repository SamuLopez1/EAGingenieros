import { request } from "./client";
import type { Outcome } from "./comparison";
import type { Citation } from "./requirements";

export type SavedOpportunity = { id: number; title: string | null; reference: string | null; available: boolean };
export type Shortlist = { revision: number; items: SavedOpportunity[] };
export type Column = {
  opportunity: SavedOpportunity;
  reception_at: string | null;
  deadlines: Citation[];
  published_budget: { amount: string; dataset: string; field: string } | null;
  gaps: {
    status: "sin_generar" | "borrador" | "aprobado" | "invalidado";
    revision: number;
    assessed: number;
    incomplete: boolean;
    items: { kind: "habilitante" | "evaluable" | "obligacion"; outcome: Outcome; reason: string; citation: Citation }[];
  } | null;
  personnel: {
    status: "listo" | "comparacion_pendiente";
    availability_pending: boolean;
    roles: {
      role: string; confirmed_periods: number; pending: boolean;
      gaps: { start: string; end: string; shortfall_percent: string }[];
    }[];
  } | null;
  margins: {
    name: string; version: number; currency: string;
    status: "calculado" | "pendiente" | "ingreso_cero" | "desactualizado";
    review_status: "revisado" | "pendiente" | "desactualizado";
    margin_percent: string | null;
    missing_amounts: string[];
    missing_sources: string[];
  }[];
};
export type ComparisonTable = { revision: number; columns: Column[] };

const path = "/api/v1/opportunity-shortlist";
export async function fetchShortlist(signal?: AbortSignal) {
  return request<Shortlist>(path, { signal });
}
export async function putShortlist(revision: number, ids: number[]) {
  return request<Shortlist>(path, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ revision, opportunity_ids: ids }),
  });
}
export async function fetchShortlistComparison(signal?: AbortSignal) {
  return request<ComparisonTable>(`${path}/comparison`, { signal });
}
