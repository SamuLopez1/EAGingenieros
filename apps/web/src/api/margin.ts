import { request } from "./client";

export const costs = {
  direct: "Costos directos",
  indirect: "Costos indirectos",
  internal_staff: "Personal interno",
  hiring: "Contratación adicional",
  contingency: "Contingencia",
};
export const labels = { income: "Ingreso estimado", ...costs };
export type CostName = keyof typeof costs;
export type Assumption = { amount: string | null; source: string | null };
type CostInputs = Record<CostName, Assumption>;
export type Currency = "COP" | "USD" | "EUR";
export type Inputs = {
  name: string; currency: Currency; income_mode: "estimado" | "presupuesto_publicado";
  income: Assumption; costs: CostInputs;
};
type Basis = {
  published_budget: { amount: string; dataset: string; field: string } | null;
  comparison_revision: number | null;
  comparison_fingerprint: string;
  profile_version: number;
  staffing_revision: number | null;
  document_versions: { id: string; version: number; sha256: string }[];
  hiring_needs: { role: string; start: string; end: string; shortfall_percent: string }[];
  availability_pending: boolean;
};
export type Scenario = {
  id: string; version: number; actor_id: string; updated_at: string;
  event: "edicion" | "revision"; reason: string | null;
  review_status: "pendiente" | "revisado" | "desactualizado"; inputs: Inputs; basis: Basis;
  rules_version: string;
  calculation: {
    status: "pendiente" | "calculado" | "ingreso_cero";
    missing_amounts: (keyof typeof labels)[];
    missing_sources: (keyof typeof labels)[];
    total_cost: string | null; profit: string | null; margin_percent: string | null;
  };
};
export type MarginWorkspace = { basis: Basis; scenarios: Scenario[]; max_scenarios: number; can_review: boolean };
type Write = Inputs & { base_version: number; published_amount: string | null; reason: string | null };
const base = (id: number) => `/api/v1/opportunities/${id}/margin`;
const scenario = (op: number, id: string) => `${base(op)}/${encodeURIComponent(id)}`;
export function fetchMargin(op: number, signal?: AbortSignal) {
  return request<MarginWorkspace>(base(op), { signal });
}
function send<T>(path: string, method: string, body: object) {
  return request<T>(path, {
    method, body: JSON.stringify(body), headers: { "Content-Type": "application/json" },
  });
}
export function saveScenario(op: number, id: string | undefined, inputs: Write) {
  return send<Scenario>(id ? scenario(op, id) : base(op), id ? "PUT" : "POST", inputs);
}
export function fetchHistory(op: number, id: string) {
  return request<Scenario[]>(`${scenario(op, id)}/versions`);
}
export function reviewScenario(op: number, item: Scenario, reason: string) {
  return send<Scenario>(`${scenario(op, item.id)}/review`, "POST", {
    base_version: item.version, reason,
  });
}
