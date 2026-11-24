import { request, requestResponse } from "./client";

export type DocumentKind = "pliego" | "adenda";

export type DossierDocument = {
  id: string;
  opportunity_id: number;
  kind: DocumentKind;
  title: string;
  filename: string;
  origin: "manual" | "oficial";
  source_record_id: string | null;
  source_verified_at: string | null;
  version: number;
  sha256: string;
  size_bytes: number;
  status: "disponible" | "cuarentena" | "rechazado" | "vencido";
  under_review: boolean;
  uploaded_at: string;
  retention_until: string;
};

type OfficialDocument = {
  id: string;
  kind: DocumentKind;
  title: string;
  source_record_id: string;
  verified_at: string;
};

export type Dossier = {
  documents: DossierDocument[];
  official: OfficialDocument[];
  missing_pliego: boolean;
  max_file_bytes: number;
};

const base = (id: number) => `/api/v1/opportunities/${id}/documents`;

export function fetchDossier(id: number, signal: AbortSignal) {
  return request<Dossier>(base(id), { signal });
}

export function uploadDocument(id: number, kind: DocumentKind, title: string, file: File) {
  return request<DossierDocument>(`${base(id)}?kind=${kind}`, {
    method: "POST",
    headers: {
      "Content-Type": file.type || "application/octet-stream",
      "X-Document-Name": encodeURIComponent(file.name),
      "X-Document-Title": encodeURIComponent(title),
    },
    body: file,
  });
}

export function importOfficial(id: number, reference: string) {
  return request<DossierDocument>(`${base(id)}/official/${encodeURIComponent(reference)}`, {
    method: "POST",
  });
}

export function updateDocument(id: number, doc: string, action: "review" | "rescan") {
  return request<DossierDocument>(`${base(id)}/${encodeURIComponent(doc)}/${action}`, {
    method: "POST",
  });
}

export async function downloadDocument(id: number, doc: DossierDocument, signal?: AbortSignal) {
  const resource = `${base(id)}/${encodeURIComponent(doc.id)}`;
  const grant = await request<{ url: string }>(`${resource}/download-link`, { method: "POST", signal });
  const [path, ticket] = grant.url.split("#");
  if (path !== `${resource}/content` || !ticket) throw new Error("Enlace de descarga inválido.");
  const response = await requestResponse(path, {
    headers: { "X-Document-Ticket": ticket },
    signal,
  });
  return response.blob();
}
