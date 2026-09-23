/**
 * Cliente HTTP de la API.
 *
 * Un valor vacío o solo con espacios en `VITE_API_BASE_URL` se trata como no
 * configurado: sin esto, la ruta relativa se resolvería contra el servidor web
 * en lugar del proxy y todas las peticiones fallarían con 404.
 *
 * Todas las rutas del navegador viven bajo `/api`. No es una convención
 * decorativa: es el prefijo real de FastAPI y lo único que el proxy cubre, en
 * desarrollo (Vite) y en el contenedor (nginx). El servidor no reescribe el
 * prefijo, así que desarrollo y despliegue resuelven las mismas rutas.
 */

import type {
  Health,
  Opportunity,
  OpportunityFilters,
  OpportunityPage,
  SessionResponse,
  SourceCoverageResponse,
  SyncRun,
  SyncTriggerResult,
  TokenResponse,
} from "./contracts";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "../auth/tokens";

const rawBase = import.meta.env.VITE_API_BASE_URL;
const configuredBase = typeof rawBase === "string" ? rawBase.trim() : "";
/** Cadena vacía en lugar de `undefined`: `undefined` haría que la ruta quedara
 *  como "undefined/api/health". */
const BASE = configuredBase.replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** El usuario no está autenticado o su sesión caducó. */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** El usuario está autenticado pero no tiene permiso. */
  get isForbidden(): boolean {
    return this.status === 403;
  }

  /** La funcionalidad no está configurada en el servidor. */
  get isUnavailable(): boolean {
    return this.status === 503;
  }
}

/** Se notifica cuando la sesión deja de ser utilizable, para volver al acceso. */
type SessionExpiredHandler = () => void;

let onSessionExpired: SessionExpiredHandler | null = null;

export function setSessionExpiredHandler(handler: SessionExpiredHandler | null): void {
  onSessionExpired = handler;
}

async function readDetail(response: Response): Promise<string | undefined> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Refresco en curso, compartido.
 *
 * Sin esto, cinco peticiones que reciben 401 a la vez dispararían cinco
 * refrescos. El servidor rota el token de refresco y detecta la reutilización
 * de uno ya usado revocando la familia completa, así que cinco refrescos
 * simultáneos cerrarían la sesión del usuario —justo lo contrario de lo que se
 * pretende—.
 */
let refreshInFlight: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  const token = getRefreshToken();
  if (!token) return false;

  if (refreshInFlight === null) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${BASE}/api/v1/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ refresh_token: token }),
        });
        if (!response.ok) {
          clearTokens();
          return false;
        }
        const tokens = (await response.json()) as TokenResponse;
        setTokens(tokens.access_token, tokens.refresh_token);
        return true;
      } catch {
        // Un fallo de red no demuestra que la sesión sea inválida, pero sin
        // poder comprobarlo tampoco se puede seguir: se cierra y se vuelve al
        // acceso, que es un estado del que el usuario sabe salir.
        clearTokens();
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  /** Evita el intento de refresco. Se usa en el propio refresco y al acceder. */
  skipRefresh?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal, skipRefresh = false } = options;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const access = getAccessToken();
  if (access) headers.Authorization = `Bearer ${access}`;

  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });

  if (response.status === 401 && !skipRefresh) {
    // Un 401 significa «el token no sirve», no «el usuario no tiene permiso».
    // Se intenta refrescar una vez y se repite la petición original.
    const refreshed = await refreshSession();
    if (refreshed) {
      return request<T>(path, { ...options, skipRefresh: true });
    }
    onSessionExpired?.();
    throw new ApiError("La sesión caducó. Vuelva a iniciar sesión.", 401);
  }

  if (!response.ok) {
    const detail = await readDetail(response);
    throw new ApiError(
      detail ?? `La API respondió ${response.status}`,
      response.status,
      detail,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// --- Autenticación ---------------------------------------------------------

export async function login(email: string, password: string): Promise<TokenResponse> {
  const tokens = await request<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: { email, password },
    skipRefresh: true,
  });
  setTokens(tokens.access_token, tokens.refresh_token);
  return tokens;
}

export async function logout(): Promise<void> {
  const token = getRefreshToken();
  try {
    if (token) {
      await request<void>("/api/v1/auth/logout", {
        method: "POST",
        body: { refresh_token: token },
        skipRefresh: true,
      });
    }
  } finally {
    // La sesión local se cierra siempre. Si el servidor no pudo revocar el
    // token, dejar la sesión abierta en el navegador sería peor: el usuario
    // creería haber salido.
    clearTokens();
  }
}

export function fetchSession(signal?: AbortSignal): Promise<SessionResponse> {
  return request<SessionResponse>("/api/v1/auth/session", { signal });
}

// --- Sistema ---------------------------------------------------------------

export function fetchHealth(signal?: AbortSignal): Promise<Health> {
  return request<Health>("/api/health", { signal });
}

// --- Fuentes y oportunidades ----------------------------------------------

export function fetchSources(signal?: AbortSignal): Promise<SourceCoverageResponse> {
  return request<SourceCoverageResponse>("/api/v1/sources", { signal });
}

/** Serializa los filtros omitiendo los vacíos.
 *
 * Un filtro sin valor no debe viajar como cadena vacía: el servidor lo
 * interpretaría como «filtrar por vacío» y devolvería un subconjunto
 * silenciosamente equivocado en lugar de no filtrar.
 */
export function buildOpportunityQuery(
  filters: OpportunityFilters = {},
  page: { limit?: number; offset?: number } = {},
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (typeof value === "string" && value.trim()) {
      search.set(key, value.trim());
    }
  }
  if (page.limit !== undefined) search.set("limit", String(page.limit));
  if (page.offset !== undefined) search.set("offset", String(page.offset));
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function fetchOpportunities(
  params: { filters?: OpportunityFilters; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<OpportunityPage> {
  const query = buildOpportunityQuery(params.filters ?? {}, {
    limit: params.limit,
    offset: params.offset,
  });
  return request<OpportunityPage>(`/api/v1/opportunities${query}`, { signal });
}

export function fetchOpportunity(
  id: number,
  signal?: AbortSignal,
): Promise<Opportunity> {
  return request<Opportunity>(`/api/v1/opportunities/${id}`, { signal });
}

// --- Sincronización --------------------------------------------------------

export function triggerSync(
  params: { dataset?: string; limit?: number } = {},
  signal?: AbortSignal,
): Promise<SyncTriggerResult> {
  const search = new URLSearchParams();
  if (params.dataset) search.set("dataset", params.dataset);
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
