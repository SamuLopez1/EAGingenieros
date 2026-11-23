import { request } from "./client";
import type { Outcome } from "./comparison";
import type { Citation } from "./requirements";

export type DemandFields = {
  role: string | null;
  dedication: string | null;
  start: string | null;
  end: string | null;
};

type Evidence = { document_id: string; locator: string };
export type StaffingPlan = {
  status: "listo" | "comparacion_pendiente";
  profile_version: number;
  comparison_revision: number;
  fingerprint: string;
  document_versions: { id: string; version: number; sha256: string }[];
  incomplete: boolean;
  can_correct: boolean;
  service_fit: {
    line: string | null;
    status: "respaldado" | "por_confirmar";
    reason: string;
    citations: Citation[];
    support: { title: string; category: "experiencia" | "capacidad"; evidence: Evidence[] }[];
  }[];
  qualifying_gaps: { citation: Citation; outcome: Outcome; reason: string }[];
  demands: (DemandFields & { row_id: string; citation: Citation; missing: string[]; corrected: boolean })[];
  roles: {
    role: string;
    periods: {
      start: string; end: string; required: string; recorded: string | null; shortfall: string | null;
      status: "confirmada" | "insuficiente" | "por_confirmar"; reason: string;
      evaluate_staffing: boolean; verify_availability: boolean;
      demand_ids: string[]; evidence: Evidence[];
    }[];
  }[];
  audit: {
    sequence: number; comparison_revision: number; actor_id: string; created_at: string;
    row_id: string; reason: string; previous: DemandFields; corrected: DemandFields;
  }[];
};

const resource = (id: number) => `/api/v1/opportunities/${id}/staffing`;
export function fetchStaffing(id: number, signal?: AbortSignal) {
  return request<StaffingPlan>(resource(id), { signal });
}
export function correctStaffing(id: number, snapshot: StaffingPlan, fields: DemandFields & {
  row_id: string; reason: string;
}) {
  return request<StaffingPlan>(`${resource(id)}/corrections`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...fields, revision: snapshot.comparison_revision, fingerprint: snapshot.fingerprint,
      expected_event: snapshot.audit[0]?.sequence ?? 0,
    }),
  });
}
