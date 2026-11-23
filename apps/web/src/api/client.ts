/**
 * Cliente HTTP de la API.
 *
 * Un valor vacío o solo con espacios en `VITE_API_BASE_URL` se trata como no
 * configurado: sin esto, la ruta relativa se resolvería contra el servidor web
 * en lugar del proxy de desarrollo y todas las peticiones fallarían con 404.
 */

import type {
  Opportunity,
  OpportunityPage,
  SyncTriggerResult,
  FilterCriteria,
  SavedFilter,
} from "./contracts";

const rawBase = import.meta.env.VITE_API_BASE_URL;
const configuredBase = typeof rawBase === "string" ? rawBase.trim() : "";
/** Cadena vacía en lugar de `undefined`: `undefined` haría que la ruta quedara
 *  como "undefined/health". */
// Vite conserva /api para negocio y retira solo el prefijo de las rutas Auth.
const BASE = configuredBase.replace(/\/+$/, "");

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
  const { browserAuthClient } = await import("../auth");
  const token = await browserAuthClient.getAccessToken?.();
  if (!token) throw new ApiError("La sesión ha terminado.", 401);
  const url = `${BASE.endsWith("/api") ? BASE.slice(0, -4) : BASE}${path}`;
  const response = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new ApiError(
      `La API respondió ${response.status}`,
      response.status,
    );
  }
  return response.status === 204 ? (undefined as T) : (await response.json()) as T;
}

export function fetchOpportunities(
  params: Partial<FilterCriteria> & { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<OpportunityPage> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  }
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

export function fetchFilterOptions(signal?: AbortSignal) {
  return request<{ statuses: string[]; modalities: string[] }>("/api/v1/opportunity-options", { signal });
}

export function fetchSavedFilters(signal?: AbortSignal) {
  return request<SavedFilter[]>("/api/v1/opportunity-filters", { signal });
}

export function saveFilter(name: string, criteria: FilterCriteria, id?: number) {
  return request<SavedFilter>(`/api/v1/opportunity-filters${id ? `/${id}` : ""}`, {
    method: id ? "PUT" : "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, criteria }),
  });
}

export function deleteFilter(id: number) {
  return request<void>(`/api/v1/opportunity-filters/${id}`, { method: "DELETE" });
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
