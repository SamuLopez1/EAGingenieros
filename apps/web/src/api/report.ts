import { request, requestResponse } from "./client";

type MailState = "en_curso" | "aceptado" | "reintentar" | "rechazado" | "incierto" | "bloqueado";
export type Delivery = {
  id: string; recipient: string; revision: number; state: MailState;
  updated_at: string; provider_id: string | null;
  attempts: { actor_id: string; started_at: string; finished_at: string | null; state: MailState }[];
};
type Outbox = { configured: boolean; recipients: string[]; deliveries: Delivery[] };
const resource = (id: number, revision: number) => `/api/v1/opportunities/${id}/reports/${revision}`;

export async function fetchReport(id: number, revision: number, download = false) {
  const response = await requestResponse(resource(id, revision) + (download ? "?download=true" : ""));
  return response.blob();
}
export function fetchOutbox(id: number, revision: number, signal?: AbortSignal) {
  return request<Outbox>(`${resource(id, revision)}/mail`, { signal });
}
export function sendReport(id: number, revision: number, recipient: string) {
  return request<Delivery>(`${resource(id, revision)}/mail`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ recipient }),
  });
}
