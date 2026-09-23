/**
 * Contratos de la API.
 *
 * Espejo de `apps/api/app/api/contracts.py`. Cuando el contrato crezca, estos
 * tipos deben generarse desde `openapi.json` en lugar de mantenerse a mano.
 *
 * Regla que atraviesa todo el archivo: un valor ausente es `null`, nunca `0`
 * ni cadena vacía. «No sé cuánto vale» y «vale cero» son hechos distintos, y
 * confundirlos produce una lectura equivocada de la licitación.
 */

export type ComparisonState =
  | "cumple"
  | "cumple_parcialmente"
  | "no_cumple"
  | "revision_manual";

/** Plataformas de contratación pública que el sistema consulta. */
export type Platform = "SECOP_I" | "SECOP_II";

/** Estado de cobertura que el sistema declara sobre una fuente. */
export type CoverageState =
  | "sincronizada"
  | "parcial"
  | "historica"
  | "no_sincronizada";

export interface Opportunity {
  id: number;
  source_dataset: string;
  source_id: string;
  reference: string | null;
  title: string | null;
  entity: string | null;
  status: string | null;
  modality: string | null;
  published_at: string | null;
  last_updated_at: string | null;
  official_url: string | null;
  first_seen_at: string;
  last_synced_at: string;

  // --- Procedencia ---
  // Viaja en cada fila, no solo en un encabezado: al mezclar dos plataformas
  // en una misma tabla, la única forma de saber de dónde viene una
  // oportunidad es que lo diga la propia fila.
  platform: Platform;
  platform_label: string;
  entity_nit: string | null;

  // --- Valor económico ---
  // `amount_label` acompaña siempre al número porque `precio_base` (SECOP II)
  // y `cuantia_proceso` (SECOP I) NO miden lo mismo. Presentarlos bajo una
  // etiqueta común afirmaría una equivalencia que no existe.
  amount: number | null;
  amount_label: string;

  // --- Posible duplicado entre fuentes ---
  // Señal, nunca fusión. El sistema no colapsa dos filas por su cuenta.
  group_key: string | null;
  possible_duplicate: boolean;
  duplicate_platforms: string[];
}

export interface OpportunityPage {
  items: Opportunity[];
  total: number;
  limit: number;
  offset: number;
}

/** Filtros del listado. Todos opcionales; `undefined` significa «sin filtrar». */
export interface OpportunityFilters {
  platform?: Platform;
  source?: string;
  entity_nit?: string;
  estado?: string;
  modalidad?: string;
  desde?: string;
  hasta?: string;
  q?: string;
}

export interface SourceCoverage {
  dataset: string;
  platform: Platform;
  label: string;
  short_label: string;
  coverage: CoverageState;
  note: string;
  opportunity_count: number;
  amount_label: string;
}

export interface SourceCoverageResponse {
  sources: SourceCoverage[];
}

export interface SyncTriggerResult {
  outcome: string;
  run_id: number | null;
  records_seen: number;
  records_created: number;
  records_updated: number;
  records_unchanged: number;
  requests_made: number;
  last_offset: number;
  error_kind: string | null;
  notes: string[];
}

export interface SyncRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  outcome: string;
  trigger: string;
  dataset: string;
  records_seen: number;
  records_created: number;
  records_updated: number;
  records_skipped: number;
  requests_made: number;
  last_offset: number;
  error_kind: string | null;
}

export interface Health {
  status: "ok";
  version: string;
  environment: string;
  /** "database" o "memory". Se muestra para no confundir una demostración en
   *  memoria con un entorno con persistencia real. */
  persistence: "database" | "memory";
  embeddings: "proveedor_externo" | "local_sin_semantica";
}

// --- Autenticación ---------------------------------------------------------

export type Role = "administrador" | "analista";

export interface SessionUser {
  user_id: number;
  email: string;
  display_name: string | null;
  role: Role;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: SessionUser;
}

export interface SessionResponse {
  user_id: number;
  email: string;
  display_name: string | null;
  role: Role;
  organization_id: string;
}
