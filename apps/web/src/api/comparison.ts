import { request } from "./client";
import type { Finding } from "./requirements";

export const outcomes = {
  cumple: "Cumple",
  cumple_parcialmente: "Cumple parcialmente",
  no_cumple: "No cumple",
  revision_manual: "Revisión manual",
};
export type Outcome = keyof typeof outcomes;
export type ProfileSource = {
  index: number;
  title: string;
  evidence: { document_id: string; locator: string }[];
};
export type Row = Finding & {
  id: string;
  outcome: Outcome;
  reason: string;
  profile_sources: ProfileSource[];
  corrected: boolean;
};
type Audit = {
  revision: number;
  action: "generado" | "corregido" | "aprobado";
  actor_id: string;
  actor_role: string;
  created_at: string;
  profile_version: number;
  document_versions: { id: string; version: number; sha256: string }[];
  before: Outcome | null;
  after: Outcome | null;
  reason: string | null;
};
export type Comparison = {
  revision: number;
  fingerprint: string;
  profile_version: number;
  status: "sin_generar" | "borrador" | "aprobado" | "invalidado";
  invalidated_by: string[];
  incomplete: boolean;
  warnings: string[];
  rows: Row[];
  profile_options: ProfileSource[];
  audit: Audit[];
};

const resource = (id: number) => `/api/v1/opportunities/${id}/comparison`;
export function readComparison(id: number, signal?: AbortSignal) {
  return request<Comparison>(resource(id), { signal });
}
export function compare(id: number) {
  return request<Comparison>(resource(id), { method: "POST" });
}
function write(id: number, snapshot: Comparison, action: "approve" | "corrections", fields: object) {
  return request<Comparison>(`${resource(id)}/${action}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ revision: snapshot.revision, fingerprint: snapshot.fingerprint, ...fields }),
  });
}
export function correctComparison(id: number, snapshot: Comparison, correction: {
  row_id: string; outcome: Outcome; reason: string; profile_entry: number | null;
}) {
  return write(id, snapshot, "corrections", correction);
}
export function approveComparison(id: number, snapshot: Comparison, reason: string) {
  return write(id, snapshot, "approve", { reason });
}
