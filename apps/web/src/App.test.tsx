import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type { OpportunityPage, SyncTriggerResult } from "./api/contracts";

const HEALTH = {
  status: "ok",
  version: "0.1.0",
  environment: "test",
  persistence: "database",
};

function opportunity(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    source_dataset: "p6dx-8zbt",
    source_id: "CO1.REQ.1",
    reference: "REF-1",
    title: "Prestación de servicios",
    entity: "E.S.E. Hospital Local",
    status: "Publicado",
    modality: "Contratación directa",
    published_at: "2026-01-28T00:00:00Z",
    last_updated_at: "2026-01-29T00:00:00Z",
    official_url: "https://community.secop.gov.co/x",
    first_seen_at: "2026-09-17T10:00:00Z",
    last_synced_at: new Date().toISOString(),
    ...overrides,
  };
}

function page(items: unknown[], total?: number): OpportunityPage {
  return {
    items: items as OpportunityPage["items"],
    total: total ?? items.length,
    limit: 25,
    offset: 0,
  };
}

const SYNC_OK: SyncTriggerResult = {
  outcome: "completed",
  run_id: 1,
  records_seen: 1,
  records_created: 1,
  records_updated: 0,
  records_unchanged: 0,
  requests_made: 1,
  last_offset: 1,
  error_kind: null,
  notes: [],
};

/** Responde según la ruta solicitada, para no acoplar los tests al orden. */
function stubApi(
  handlers: {
    health?: unknown;
    opportunities?: unknown;
    sync?: unknown;
  } = {},
) {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.includes("/health")
      ? (handlers.health ?? HEALTH)
      : url.includes("/sync-runs")
        ? (handlers.sync ?? SYNC_OK)
        : (handlers.opportunities ?? page([opportunity()]));
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("listado de oportunidades", () => {
  it("muestra el estado de carga antes de recibir datos", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));

    render(<App />);

    expect(screen.getByText("Cargando oportunidades…")).toBeInTheDocument();
  });

  it("muestra las oportunidades sincronizadas", async () => {
    stubApi();

    render(<App />);

    expect(await screen.findByText("E.S.E. Hospital Local")).toBeInTheDocument();
    expect(screen.getByText("Prestación de servicios")).toBeInTheDocument();
    expect(screen.getByText("REF-1")).toBeInTheDocument();
  });

  it("declara el modo de persistencia de la API", async () => {
    stubApi();

    render(<App />);

    expect(await screen.findByText("Base de datos")).toBeInTheDocument();
  });

  it("advierte cuando la API funciona en memoria", async () => {
    stubApi({ health: { ...HEALTH, persistence: "memory" } });

    render(<App />);

    expect(await screen.findByText("Modo memoria")).toBeInTheDocument();
  });

  it("explica el vacío en lugar de mostrar una tabla sin filas", async () => {
    stubApi({ opportunities: page([]) });

    render(<App />);

    expect(
      await screen.findByText("No hay oportunidades sincronizadas."),
    ).toBeInTheDocument();
  });

  it("explica el fallo de la API sin dejar la pantalla en blanco", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("{}", { status: 500 }))),
    );

    render(<App />);

    expect(
      await screen.findByText("No fue posible consultar las oportunidades."),
    ).toBeInTheDocument();
  });

  it("traduce el 503 a un mensaje sobre la persistencia", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("{}", { status: 503 }))),
    );

    render(<App />);

    expect(
      await screen.findByText("La persistencia no está configurada en la API."),
    ).toBeInTheDocument();
  });
});

describe("valores desconocidos", () => {
  it("muestra un guion en lugar de celda vacía", async () => {
    // Regla del sistema de diseño: un dato desconocido no es cero.
    stubApi({
      opportunities: page([
        opportunity({ reference: null, modality: null, published_at: null }),
      ]),
    });

    render(<App />);

    await screen.findByText("E.S.E. Hospital Local");
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });
});

describe("sincronización", () => {
  it("informa el resultado de una sincronización con novedades", async () => {
    stubApi({
      sync: { ...SYNC_OK, records_seen: 3, records_created: 3, last_offset: 3 },
    });
    const user = userEvent.setup();

    render(<App />);
    await screen.findByText("E.S.E. Hospital Local");
    await user.click(screen.getByRole("button", { name: "Sincronizar ahora" }));

    expect(await screen.findByText(/3 oportunidades nuevas/)).toBeInTheDocument();
  });

  it("informa cuando no hubo novedades", async () => {
    stubApi({
      sync: { ...SYNC_OK, records_created: 0, records_unchanged: 1 },
    });
    const user = userEvent.setup();

    render(<App />);
    await screen.findByText("E.S.E. Hospital Local");
    await user.click(screen.getByRole("button", { name: "Sincronizar ahora" }));

    expect(await screen.findByText(/Sin novedades/)).toBeInTheDocument();
  });

  it("declara el fallo sin fingir éxito", async () => {
    stubApi({
      sync: {
        ...SYNC_OK,
        outcome: "failed",
        records_created: 0,
        error_kind: "quota_exceeded",
      },
    });
    const user = userEvent.setup();

    render(<App />);
    await screen.findByText("E.S.E. Hospital Local");
    await user.click(screen.getByRole("button", { name: "Sincronizar ahora" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("quota_exceeded");
    expect(alert).toHaveTextContent("El catálogo no se modificó");
  });
});

describe("paginación", () => {
  it("deshabilita «Anterior» en la primera página", async () => {
    stubApi({ opportunities: page([opportunity()], 40) });

    render(<App />);
    await screen.findByText("E.S.E. Hospital Local");

    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeEnabled();
  });

  it("indica el rango visible sobre el total", async () => {
    stubApi({ opportunities: page([opportunity()], 40) });

    render(<App />);

    expect(await screen.findByText("1–1 de 40")).toBeInTheDocument();
  });

  it("no muestra paginación cuando no hay resultados", async () => {
    stubApi({ opportunities: page([]) });

    render(<App />);
    await screen.findByText("No hay oportunidades sincronizadas.");

    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});

describe("nota de alcance", () => {
  it("declara que la relación entre conjuntos no está confirmada", async () => {
    stubApi();

    render(<App />);

    await waitFor(() =>
      expect(screen.getByText(/no está confirmada/i)).toBeInTheDocument(),
    );
  });
});
