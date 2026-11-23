import { request } from "./client";
import type { Locator } from "./extraction";

export type Citation = {
  document_id: string;
  version: number;
  sha256: string;
  title: string;
  locator: Locator;
  quote: string;
};
export type Finding = {
  kind: "objeto" | "entregable" | "plazo" | "alerta" | "habilitante" | "evaluable" | "obligacion";
  citation: Citation;
};
export type Analysis = {
  schema_version: string;
  adapter: string;
  fingerprint: string;
  status: "revision_manual" | "borrador";
  incomplete: boolean;
  summary: Finding[];
  requirements: Finding[];
  warnings: { code: string; documents: string[]; citations: Citation[] }[];
};

export function analyzeDossier(opportunityId: number) {
  return request<Analysis>(`/api/v1/opportunities/${opportunityId}/requirements`, { method: "POST" });
}
