export type Validity = "abierto" | "cerrado" | "vencido" | "desconocida";

export interface Opportunity {
  id: number;
  source_dataset: string;
  source_id: string;
  reference: string | null;
  title: string | null;
  entity: string | null;
  department: string | null;
  city: string | null;
  phase: string | null;
  validity: Validity;
  reception_at: string | null;
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
  catalog_synced_at?: string | null;
  latest_sync_outcome?: string | null;
  latest_sync_finished_at?: string | null;
  catalog_stale_after_hours?: number;
}

export type FilterCriteria = {
  q: string;
  entity: string;
  location: string;
  validity: Validity | null;
  closing_from: string | null;
  closing_to: string | null;
  status: string;
  modality: string;
  published_from: string | null;
  published_to: string | null;
  sort: "published_desc" | "published_asc" | "entity_asc" | "title_asc" | "synced_desc";
};

export interface SavedFilter {
  id: number;
  name: string;
  criteria: FilterCriteria;
  updated_at: string;
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
