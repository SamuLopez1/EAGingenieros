import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import OpportunitiesPage from "./OpportunitiesPage";
import type { Opportunity, OpportunityPage } from "./api/contracts";
import * as api from "./api/client";

vi.mock("./api/client", async (original) => ({
  ...(await original<typeof api>()),
  fetchOpportunities: vi.fn(),
  fetchOpportunity: vi.fn(),
  fetchFilterOptions: vi.fn(),
  fetchSavedFilters: vi.fn(),
  saveFilter: vi.fn(),
  deleteFilter: vi.fn(),
  triggerSync: vi.fn(),
}));
const item: Opportunity = {
  id: 42,
  source_id: "SYNTH-42",
  source_dataset: "p6dx-8zbt",
  title: "Puente sintético",
  entity: "Entidad Norte",
  department: "Cundinamarca",
  city: "Bogotá",
  phase: "Presentación de oferta",
  reception_at: "2026-10-02T12:30:00Z",
  validity: "abierto",
  reference: "REF-42",
  status: "Publicado",
  modality: "Concurso",
  published_at: "2026-09-02T00:00:00Z",
  last_updated_at: null,
  official_url: "https://community.secop.gov.co/synthetic/process/42",
  first_seen_at: "2026-10-01T00:00:00Z",
  last_synced_at: "2026-10-01T00:00:00Z",
};
const page: OpportunityPage = {
  items: [item],
  total: 30,
  limit: 10,
  offset: 10,
  catalog_synced_at: "2026-10-01T00:00:00Z",
  latest_sync_outcome: "failed",
};

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  vi.mocked(api.fetchOpportunities).mockResolvedValue(page);
  vi.mocked(api.fetchOpportunity).mockResolvedValue(item);
  vi.mocked(api.fetchFilterOptions).mockResolvedValue({
    statuses: ["Publicado"],
    modalities: ["Concurso"],
  });
  vi.mocked(api.fetchSavedFilters).mockResolvedValue([]);
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("consulta la API y conserva todos los parámetros al abrir detalle y volver", async () => {
  const initial =
    "?q=puente&entity=Norte&location=Bogot%C3%A1&closing_from=2026-10-02&closing_to=2026-10-02&status=Publicado&modality=Concurso&published_from=2026-09-01&published_to=2026-09-30&sort=entity_asc&limit=10&page=2";
  window.history.replaceState(null, "", `/${initial}`);
  render(<OpportunitiesPage role="analista" />);
  const link = await screen.findByRole("link", { name: "Puente sintético" });
  expect(api.fetchOpportunities).toHaveBeenCalledWith(
    expect.objectContaining({
      q: "puente",
      entity: "Norte",
      location: "Bogotá",
      closing_from: "2026-10-02",
      closing_to: "2026-10-02",
      offset: 10,
      limit: 10,
      sort: "entity_asc",
      status: "Publicado",
    }),
    expect.any(AbortSignal),
  );
  fireEvent.click(link);
  expect(await screen.findByRole("link", { name: /Ver proceso en SECOP/ })).toHaveAttribute(
    "href",
    item.official_url,
  );
  expect(api.fetchOpportunity).toHaveBeenCalledWith(42, expect.any(AbortSignal));
  expect(screen.getByText("SYNTH-42")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("link", { name: /Volver al listado/ }));
  expect(await screen.findByRole("link", { name: "Puente sintético" })).toBeInTheDocument();
  expect(window.location.search).toBe(initial);
  expect(screen.getByLabelText("Buscar")).toHaveValue("puente");
  expect(screen.getByLabelText("Entidad", { exact: true })).toHaveValue("Norte");
  expect(screen.getByLabelText("Ubicación de la entidad")).toHaveValue("Bogotá");
  expect(screen.getByLabelText("Cierre desde (UTC)")).toHaveValue("2026-10-02");
  expect(screen.getByText(/30 resultados · Página 2/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Guardar nuevo" })).not.toBeInTheDocument();
  expect(screen.getByText(/la última sincronización falló/i)).toBeInTheDocument();
});

it("aplica búsqueda y fechas, reinicia la página y responde a popstate", async () => {
  window.history.replaceState(null, "", "/?page=3");
  render(<OpportunitiesPage role="analista" />);
  await screen.findByRole("link", { name: "Puente sintético" });
  fireEvent.change(screen.getByLabelText("Buscar"), { target: { value: "Entidad Norte" } });
  fireEvent.change(screen.getByLabelText("Publicación desde (UTC)"), {
    target: { value: "2026-09-01" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Aplicar filtros" }));
  await waitFor(() =>
    expect(api.fetchOpportunities).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: "Entidad Norte", published_from: "2026-09-01", offset: 0 }),
      expect.any(AbortSignal),
    ),
  );
  expect(new URLSearchParams(window.location.search).has("page")).toBe(false);
  act(() => {
    window.history.replaceState(null, "", "/?q=Anterior&page=2&limit=10");
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  await waitFor(() =>
    expect(api.fetchOpportunities).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: "Anterior", offset: 10 }),
      expect.any(AbortSignal),
    ),
  );
});

it("muestra carga y vacío sin inventar procesos", async () => {
  let finish!: (value: OpportunityPage) => void;
  vi.mocked(api.fetchOpportunities).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(<OpportunitiesPage role="analista" />);
  expect(screen.getByText("Cargando oportunidades…")).toBeInTheDocument();
  await act(async () => finish({ ...page, items: [], total: 0 }));
  expect(
    await screen.findByRole("heading", { name: "No hay resultados para estos filtros" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Ver todo el catálogo" })).toBeInTheDocument();
});

it("conserva la copia anterior y señala error y datos desactualizados al fallar una recarga", async () => {
  vi.mocked(api.triggerSync).mockResolvedValue({
    outcome: "completed",
    run_id: 1,
    records_seen: 0,
    records_created: 0,
    records_updated: 0,
    records_unchanged: 0,
    requests_made: 0,
    last_offset: 0,
    error_kind: null,
    notes: [],
  });
  vi.mocked(api.fetchOpportunities)
    .mockResolvedValueOnce(page)
    .mockRejectedValue(new Error("offline"));
  render(<OpportunitiesPage role="administrador" />);
  await screen.findByRole("link", { name: "Puente sintético" });
  fireEvent.click(screen.getByRole("button", { name: "Sincronizar ahora" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Los resultados anteriores pueden estar desactualizados",
  );
  expect(screen.getByRole("link", { name: "Puente sintético" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reintentar consulta" })).toBeInTheDocument();
});

it("permite al administrador actualizar los criterios del filtro seleccionado", async () => {
  const criteria = {
    q: "puente",
    entity: "",
    location: "",
    validity: null,
    closing_from: null,
    closing_to: null,
    status: "Publicado",
    modality: "",
    published_from: null,
    published_to: null,
    sort: "published_desc" as const,
  };
  const preset = { id: 7, name: "Puentes", criteria, updated_at: "2026-10-01T00:00:00Z" };
  vi.mocked(api.fetchSavedFilters).mockResolvedValue([preset]);
  vi.mocked(api.saveFilter).mockResolvedValue(preset);
  render(<OpportunitiesPage role="administrador" />);
  await screen.findByRole("option", { name: "Puentes" });
  fireEvent.change(screen.getByRole("combobox", { name: "Filtros compartidos de EAG" }), {
    target: { value: "7" },
  });
  await screen.findByRole("link", { name: "Puente sintético" });
  fireEvent.change(screen.getByLabelText("Buscar"), { target: { value: "Puente nuevo" } });
  fireEvent.click(screen.getByRole("button", { name: "Aplicar filtros" }));
  await waitFor(() =>
    expect(api.fetchOpportunities).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: "Puente nuevo" }),
      expect.any(AbortSignal),
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "Actualizar seleccionado" }));
  await waitFor(() =>
    expect(api.saveFilter).toHaveBeenCalledWith(
      "Puentes",
      expect.objectContaining({ q: "Puente nuevo" }),
      7,
    ),
  );
});

const syncResult = {
  outcome: "completed",
  run_id: 2,
  records_seen: 6,
  records_created: 1,
  records_updated: 2,
  records_unchanged: 3,
  requests_made: 1,
  last_offset: 6,
  error_kind: null,
  notes: [],
};

it("consulta opciones nuevas tras sincronizar sin perder selección, página ni navegación", async () => {
  const initial = "?q=puente&status=Publicado&modality=Concurso&sort=entity_asc&limit=10&page=2";
  window.history.replaceState(null, "", `/${initial}`);
  vi.mocked(api.triggerSync).mockResolvedValue(syncResult);
  vi.mocked(api.fetchFilterOptions)
    .mockResolvedValueOnce({ statuses: ["Publicado"], modalities: ["Concurso"] })
    .mockResolvedValue({
      statuses: ["Publicado", "Evaluación nueva"],
      modalities: ["Concurso", "Modalidad nueva"],
    });
  render(<OpportunitiesPage role="administrador" />);
  await screen.findByRole("link", { name: "Puente sintético" });
  fireEvent.click(screen.getByRole("button", { name: "Sincronizar ahora" }));
  expect(await screen.findByRole("option", { name: "Evaluación nueva" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Modalidad nueva" })).toBeInTheDocument();
  expect(screen.getByText(/1 nuevas, 2 actualizadas, 3 sin cambios/)).toBeInTheDocument();
  expect(window.location.search).toBe(initial);
  expect(screen.getByLabelText("Estado SECOP")).toHaveValue("Publicado");
  expect(screen.getByLabelText("Modalidad")).toHaveValue("Concurso");
  expect(screen.getByText(/Página 2/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("link", { name: "Puente sintético" }));
  await screen.findByRole("link", { name: /Ver proceso en SECOP/ });
  fireEvent.click(screen.getByRole("link", { name: /Volver al listado/ }));
  await screen.findByRole("link", { name: "Puente sintético" });
  expect(window.location.search).toBe(initial);
  expect(api.fetchFilterOptions).toHaveBeenCalledTimes(2);
});

it("un error al refrescar opciones no oculta catálogo ni convierte una sincronización correcta en fallida; permite reintento", async () => {
  vi.mocked(api.triggerSync).mockResolvedValue(syncResult);
  vi.mocked(api.fetchFilterOptions)
    .mockResolvedValueOnce({ statuses: ["Publicado"], modalities: ["Concurso"] })
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue({ statuses: ["Publicado", "Nuevo estado"], modalities: ["Concurso"] });
  vi.mocked(api.fetchOpportunities).mockResolvedValue({
    ...page,
    latest_sync_outcome: "completed",
  });
  render(<OpportunitiesPage role="administrador" />);
  await screen.findByRole("option", { name: "Publicado" });
  fireEvent.click(screen.getByRole("button", { name: "Sincronizar ahora" }));
  const retry = await screen.findByRole("button", { name: "Reintentar opciones" });
  expect(await screen.findByRole("link", { name: "Puente sintético" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Publicado" })).toBeInTheDocument();
  expect(
    screen.getByText(/Carga terminada: 1 nuevas, 2 actualizadas, 3 sin cambios/),
  ).toBeInTheDocument();
  expect(screen.queryByText(/sincronización falló/)).not.toBeInTheDocument();
  fireEvent.click(retry);
  expect(await screen.findByRole("option", { name: "Nuevo estado" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Reintentar opciones" })).not.toBeInTheDocument();
});

it("permite reintentar también el fallo inicial de opciones", async () => {
  vi.mocked(api.fetchFilterOptions)
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue({ statuses: ["Publicado"], modalities: ["Concurso"] });
  render(<OpportunitiesPage role="analista" />);
  fireEvent.click(await screen.findByRole("button", { name: "Reintentar opciones" }));
  expect(await screen.findByRole("option", { name: "Publicado" })).toBeInTheDocument();
});

it("refresca opciones y expone contadores del avance cuando la sincronización informa fallo parcial", async () => {
  vi.mocked(api.triggerSync).mockResolvedValue({
    ...syncResult,
    outcome: "failed",
    error_kind: "quota_exceeded",
  });
  vi.mocked(api.fetchFilterOptions)
    .mockResolvedValueOnce({ statuses: ["Publicado"], modalities: ["Concurso"] })
    .mockResolvedValue({
      statuses: ["Publicado", "Estado de avance parcial"],
      modalities: ["Concurso"],
    });
  render(<OpportunitiesPage role="administrador" />);
  await screen.findByRole("link", { name: "Puente sintético" });
  fireEvent.click(screen.getByRole("button", { name: "Sincronizar ahora" }));
  expect(
    await screen.findByRole("option", { name: "Estado de avance parcial" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/La sincronización falló.*1 nuevas, 2 actualizadas, 3 sin cambios/),
  ).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: "Puente sintético" })).toBeInTheDocument();
});


it.each([
  ["abierto", "Abierto"],
  ["cerrado", "Cerrado"],
  ["vencido", "Vencido"],
  ["desconocida", "Vigencia desconocida"],
] as const)("muestra la vigencia %s y conserva el vínculo oficial", async (validity, label) => {
  window.history.replaceState(null, "", "/?opportunity=42");
  vi.mocked(api.fetchOpportunity).mockResolvedValue({
    ...item, validity, reception_at: validity === "desconocida" ? null : item.reception_at,
  });
  render(<OpportunitiesPage role="analista" />);
  expect(await screen.findByRole("link", { name: /Ver proceso en SECOP/ })).toBeVisible();
  const detail = screen.getByRole("region", { name: "Detalle de oportunidad" });
  expect(detail).toHaveTextContent(label);
  expect(detail).toHaveTextContent("Publicado");
});


it("omite enlaces fuera de los dominios oficiales de SECOP", async () => {
  window.history.replaceState(null, "", "/?opportunity=42");
  vi.mocked(api.fetchOpportunity).mockResolvedValue({
    ...item, official_url: "https://community.secop.gov.co.example.invalid/proceso",
  });
  render(<OpportunitiesPage role="analista" />);
  expect(await screen.findByText("La fuente no informó un enlace oficial válido.")).toBeVisible();
  expect(screen.queryByRole("link", { name: /Ver proceso en SECOP/ })).not.toBeInTheDocument();
});
