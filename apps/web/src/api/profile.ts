import { request, requestResponse } from "./client";

export const categories = {
  experiencia: "Experiencia", capacidad: "Capacidad", contrato: "Contrato",
  certificado: "Certificado", personal: "Personal", equipo: "Equipo",
  financiero: "Financiero", legal: "Legal", disponibilidad: "Disponibilidad",
};
type Evidence = { document_id: string; locator: string };
export type ProfileEntry = {
  category: keyof typeof categories;
  title: string;
  description: string;
  service_line: string | null;
  role: string | null;
  dedication_percent: string | null;
  amount: string | null;
  unit: string | null;
  starts_on: string | null;
  ends_on: string | null;
  status: "pendiente" | "verificado";
  evidence: Evidence[];
};
export type Version = { version: number; author_id: string; created_at: string };
type Profile = { version: number; availability_status: "pendiente" | "verificado"; entries: ProfileEntry[] };

const base = "/api/v1/company-profile";
export function fetchProfile(version?: number, signal?: AbortSignal) {
  return request<Profile>(version ? `${base}/versions/${version}` : base, { signal });
}
export function fetchVersions(before?: number, signal?: AbortSignal) {
  return request<Version[]>(`${base}/versions${before ? `?before=${before}` : ""}`, { signal });
}
export function saveProfile(baseVersion: number, entries: ProfileEntry[]) {
  return request<Profile>(base, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_version: baseVersion, entries }),
  });
}
export function uploadEvidence(file: File) {
  return request<{ id: string; filename: string }>(`${base}/evidence`, {
    method: "POST",
    body: file,
    headers: {
      "X-Document-Name": encodeURIComponent(file.name),
      "Content-Type": file.type || "application/octet-stream",
    },
  });
}
export async function downloadEvidence(id: string) {
  const response = await requestResponse(`${base}/evidence/${encodeURIComponent(id)}`);
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = response.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] ?? "evidencia";
  link.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
