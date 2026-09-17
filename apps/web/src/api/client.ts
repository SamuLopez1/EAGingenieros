/**
 * Cliente HTTP de la API.
 *
 * Un valor vacío o solo con espacios en `VITE_API_BASE_URL` se trata como no
 * configurado: sin esto, la ruta relativa se resolvería contra el servidor web
 * en lugar del proxy de desarrollo y todas las peticiones fallarían con 404.
 */

import type {
  Health,
  Opportunity,
  OpportunityPage,
  SyncRun,
  SyncTriggerResult,
} from "./contracts";

const rawBase = import.meta.env.VITE_API_BASE_URL;
const configuredBase = typeof rawBase === "string" ? rawBase.trim() : "";
/** Cadena vacía en lugar de `undefined`: `undefined` haría que la ruta quedara
 *  como "undefined/health". */
const BASE = configuredBase.replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
  });

  if (!response.ok) {
    throw new ApiError(
      `La API respondió ${response.status}`,
      response.status,
    );
  }
  return (await response.json()) as T;
}

export function fetchHealth(signal?: AbortSignal): Promise<Health> {
  return request<Health>("/health", { signal });
}

export function fetchOpportunities(
  params: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<OpportunityPage> {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  const query = search.toString();
  return request<OpportunityPage>(
    `/api/v1/opportunities${query ? `?${query}` : ""}`,
    { signal },
  );
}

export function fetchOpportunity(
  id: number,
  signal?: AbortSignal,
): Promise<Opportunity> {
  return request<Opportunity>(`/api/v1/opportunities/${id}`, { signal });
}

export function triggerSync(
  params: { limit?: number } = {},
  signal?: AbortSignal,
): Promise<SyncTriggerResult> {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const query = search.toString();
  return request<SyncTriggerResult>(
    `/api/v1/sync-runs${query ? `?${query}` : ""}`,
    { method: "POST", signal },
  );
}

export function fetchSyncRuns(
  params: { limit?: number } = {},
  signal?: AbortSignal,
): Promise<SyncRun[]> {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const query = search.toString();
  return request<SyncRun[]>(`/api/v1/sync-runs${query ? `?${query}` : ""}`, {
    signal,
  });
}
