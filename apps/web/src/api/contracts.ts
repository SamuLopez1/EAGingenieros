/**
 * Contratos de la API.
 *
 * Espejo de `apps/api/app/api/contracts.py`. Cuando el contrato crezca, estos
 * tipos deben generarse desde `openapi.json` en lugar de mantenerse a mano;
 * mientras el contrato es pequeño, el espejo se verifica en tiempo de ejecución
 * (ver `parse.ts`) para que una divergencia falle de forma visible.
 */

export type ComparisonState =
  | "cumple"
  | "cumple_parcialmente"
  | "no_cumple"
  | "revision_manual";

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
}

export interface OpportunityPage {
  items: Opportunity[];
  total: number;
  limit: number;
  offset: number;
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
  /** "database" o "memory". Se muestra para no confundir una demostración
   *  en memoria con un entorno con persistencia real. */
  persistence: "database" | "memory";
}
