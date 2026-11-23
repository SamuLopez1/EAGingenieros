import { request } from "./client";

export type Locator = {
  page: number | null;
  section: string | null;
  paragraph: number | null;
  table: number | null;
  row: number | null;
  column: number | null;
  sheet: string | null;
  cell: string | null;
};

export type Extraction = {
  document_id: string;
  opportunity_id: number;
  version: number;
  source_sha256: string;
  status: "sin_extraccion" | "pendiente" | "procesando" | "listo" | "revision" | "fallido";
  attempts: number;
  result: {
    total_pages: number | null;
    fragments: {
      locator: Locator;
      text: string;
      method: "texto" | "ocr";
      confidence: number | null;
    }[];
    warnings: { code: string; locator: Locator | null }[];
    error_code: string | null;
  } | null;
};

function path(opportunityId: number, documentId: string) {
  return `/api/v1/opportunities/${opportunityId}/documents/${encodeURIComponent(documentId)}/extraction`;
}

export function fetchExtraction(opportunityId: number, documentId: string, signal: AbortSignal) {
  return request<Extraction>(path(opportunityId, documentId), { signal });
}

export function requestExtraction(opportunityId: number, documentId: string, retry: boolean) {
  return request<Extraction>(
    `${path(opportunityId, documentId)}${retry ? "?retry=true" : ""}`, { method: "POST" },
  );
}
