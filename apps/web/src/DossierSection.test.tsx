import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DossierSection } from "./DossierSection";
import { downloadDocument, fetchDossier } from "./api/documents";
import type { DossierDocument } from "./api/documents";
import { analyzeDossier } from "./api/requirements";

vi.mock("./api/documents", () => ({
  fetchDossier: vi.fn(),
  downloadDocument: vi.fn(),
  importOfficial: vi.fn(),
  updateDocument: vi.fn(),
  uploadDocument: vi.fn(),
}));
vi.mock("./api/requirements", () => ({ analyzeDossier: vi.fn() }));
vi.mock("./DossierComparison", () => ({ DossierComparison: () => null }));
vi.mock("./DocumentExtraction", () => ({ DocumentExtraction: () => null }));
vi.mock("./MarginSection", () => ({ MarginSection: () => null }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("abre el PDF privado del expediente en la página citada y libera la vista al cerrar", async () => {
  const item: DossierDocument = {
    id: "pdf-19", opportunity_id: 1, kind: "pliego", title: "Pliego de prueba",
    filename: "pliego.pdf", origin: "oficial", source_record_id: "fixture",
    source_verified_at: null, version: 1, sha256: "fixture", size_bytes: 10,
    status: "disponible", under_review: true, uploaded_at: "2026-11-01T00:00:00Z",
    retention_until: "2026-12-01T00:00:00Z",
  };
  vi.mocked(fetchDossier).mockResolvedValue({
    documents: [item], official: [], missing_pliego: false, max_file_bytes: 100,
  });
  vi.mocked(analyzeDossier).mockResolvedValue({
    schema_version: "fixture", adapter: "fixture", fingerprint: "fixture",
    status: "revision_manual", incomplete: true, summary: [], warnings: [],
    requirements: [{
      kind: "habilitante",
      citation: {
        document_id: item.id, version: item.version, sha256: item.sha256,
        title: item.title, quote: "Requisito de prueba.",
        locator: {
          page: 19, section: null, paragraph: null, table: null, row: null,
          column: null, sheet: null, cell: null,
        },
      },
    }],
  });
  const blob = new Blob(["%PDF-1.4"], { type: "application/octet-stream" });
  const firstBytes = Object.assign(blob.slice(0, 5), { text: async () => "%PDF-" });
  vi.spyOn(blob, "slice").mockReturnValueOnce(firstBytes);
  const create = vi.fn(() => "blob:documento");
  const revoke = vi.fn();
  vi.stubGlobal("URL", Object.assign(class extends URL {}, {
    createObjectURL: create, revokeObjectURL: revoke,
  }));
  vi.mocked(downloadDocument).mockResolvedValue(blob);
  render(<DossierSection opportunityId={1} role="analista" />);
  fireEvent.click(await screen.findByRole("button", { name: "Generar resumen y requisitos" }));
  fireEvent.click(await screen.findByRole("button", { name: "Ver documento" }));
  expect(await screen.findByTitle("Vista previa privada del documento"))
    .toHaveAttribute("src", "blob:documento#page=19");
  expect(screen.getByRole("link", { name: "Abrir PDF en otra pestaña" }))
    .toHaveAttribute("href", "blob:documento#page=19");
  expect(downloadDocument).toHaveBeenCalledWith(1, item, expect.any(AbortSignal));
  expect(create).toHaveBeenCalledWith(expect.objectContaining({ type: "application/pdf", size: blob.size }));
  fireEvent.click(screen.getByRole("button", { name: "Cerrar vista del documento" }));
  expect(revoke).toHaveBeenCalledWith("blob:documento");
});
