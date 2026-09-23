import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { SessionProvider } from "./auth/SessionProvider";
import { clearTokens, setTokens } from "./auth/tokens";
import type { OpportunityPage, SyncTriggerResult } from "./api/contracts";

const HEALTH = {
  status: "ok",
  version: "0.1.0",
  environment: "test",
  persistence: "database",
  embeddings: "local_sin_semantica",
};

const SESSION = {
  user_id: 1,
  email: "analista@eag.local",
  display_name: "Ana Analista",
  role: "analista",
  organization_id: "00000000-0000-0000-0000-000000000002",
};

const SOURCES = {
  sources: [
    {
      dataset: "p6dx-8zbt",
      platform: "SECOP_II",
      label: "SECOP II · Procesos de contratación",
      short_label: "SECOP II",
      coverage: "sincronizada",
      note: "Plataforma vigente. Es la fuente principal del listado.",
      opportunity_count: 1,
      amount_label: "Precio base",
    },
    {
      dataset: "f789-7hwg",
      platform: "SECOP_I",
      label: "SECOP I · Procesos de compra pública",
      short_label: "SECOP I",
      coverage: "parcial",
      note: "El solapamiento con SECOP II no está establecido.",
      opportunity_count: 1,
      amount_label: "Cuantía del proceso",
    },
  ],
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
    platform: "SECOP_II",
    platform_label: "SECOP II",
    entity_nit: "891500498",
    amount: 1500000,
    amount_label: "Precio base",
    group_key: null,
    possible_duplicate: false,
    duplicate_platforms: [],
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

interface Handlers {
  health?: unknown;
  session?: unknown;
  sources?: unknown;
  opportunities?: unknown;
  /** Respuesta de `/opportunities/{id}`. Es una oportunidad suelta, no una
   *  página: confundirlas hacía fallar el detalle con datos con forma de lista. */
  detail?: unknown;
  sync?: unknown;
  sessionStatus?: number;
}

/** Responde según la ruta solicitada, para no acoplar los tests al orden. */
function stubApi(handlers: Handlers = {}) {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    const json = (body: unknown, status = 200) =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      );

    if (url.includes("/api/v1/auth/session")) {
      const status = handlers.sessionStatus ?? 200;
      return status === 200
        ? json(handlers.session ?? SESSION)
        : Promise.resolve(new Response("{}", { status }));
    }
    if (url.includes("/api/v1/sources")) return json(handlers.sources ?? SOURCES);
    if (url.includes("/api/v1/sync-runs")) return json(handlers.sync ?? SYNC_OK);
    if (url.includes("/api/health")) return json(handlers.health ?? HEALTH);
    // El detalle responde con un objeto; el listado, con una página. Se
    // distinguen por la forma de la ruta, no por el orden de las llamadas.
    if (/\/api\/v1\/opportunities\/\d+(\?|$)/.test(url)) {
      return json(handlers.detail ?? opportunity());
    }
    return json(handlers.opportunities ?? page([opportunity()]));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderApp(initialPath = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <SessionProvider>
          <App />
        </SessionProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  sessionStorage.clear();
  // La sesión se declara iniciada antes de montar: el proveedor comprueba la
  // vigencia contra la API, y sin tokens mostraría la pantalla de acceso.
  setTokens("access-token-de-prueba", "refresh-token-de-prueba");
});

afterEach(() => {
  clearTokens();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// --- Acceso ----------------------------------------------------------------

describe("acceso", () => {
  it("pide credenciales cuando no hay sesión", () => {
    clearTokens();
    stubApi();

    renderApp();

    expect(screen.getByRole("heading", { name: "Acceso" })).toBeInTheDocument();
    expect(screen.queryByText("Oportunidades")).not.toBeInTheDocument();
  });

  it("vuelve al acceso cuando la sesión guardada ya no es válida", async () => {
    stubApi({ sessionStatus: 401 });

    renderApp();

    expect(await screen.findByRole("heading", { name: "Acceso" })).toBeInTheDocument();
  });

  it("informa del fallo de credenciales sin revelar cuál es incorrecto", async () => {
    clearTokens();
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response("{}", { status: 401 })),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderApp();
    await user.type(screen.getByLabelText("Correo"), "ana@eag.local");
    await user.type(screen.getByLabelText("Contraseña"), "incorrecta");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    const alert = await screen.findByRole("alert");
    // No se distingue «el correo no existe» de «la contraseña es incorrecta»:
    // esa diferencia permitiría enumerar cuentas válidas.
    expect(alert).toHaveTextContent("Correo o contraseña incorrectos.");
  });
});

// --- Listado ---------------------------------------------------------------

describe("listado de oportunidades", () => {
  it("muestra las oportunidades sincronizadas", async () => {
    stubApi();

    renderApp();

    expect(await screen.findByText("E.S.E. Hospital Local")).toBeInTheDocument();
    expect(screen.getByText("Prestación de servicios")).toBeInTheDocument();
    expect(screen.getByText("REF-1")).toBeInTheDocument();
  });

  it("declara la procedencia en cada fila", async () => {
    stubApi();

    renderApp();

    const table = await screen.findByRole("table");
    expect(within(table).getByText("SECOP II")).toBeInTheDocument();
  });

  it("etiqueta la fuente de cada fila cuando hay varias plataformas", async () => {
    stubApi({
      opportunities: page([
        opportunity(),
        opportunity({
          id: 2,
          source_id: "UID-9",
          source_dataset: "f789-7hwg",
          platform: "SECOP_I",
          platform_label: "SECOP I",
          entity: "Alcaldía de Timbiquí",
          amount_label: "Cuantía del proceso",
        }),
      ]),
    });

    renderApp();

    const table = await screen.findByRole("table");
    expect(within(table).getByText("SECOP II")).toBeInTheDocument();
    expect(within(table).getByText("SECOP I")).toBeInTheDocument();
    // Las dos filas se muestran: el sistema no fusiona entre plataformas.
    expect(within(table).getAllByRole("row")).toHaveLength(3);
  });

  it("señala un posible duplicado sin ocultar ninguna fila", async () => {
    stubApi({
      opportunities: page([
        opportunity({ id: 1, possible_duplicate: true, duplicate_platforms: ["SECOP_I", "SECOP_II"] }),
        opportunity({ id: 2, source_id: "UID-9", possible_duplicate: true, duplicate_platforms: ["SECOP_I", "SECOP_II"], entity: "Otra entidad" }),
      ]),
    });

    renderApp();

    expect(await screen.findAllByText("Posible duplicado")).toHaveLength(2);
  });

  it("declara el modo de persistencia de la API", async () => {
    stubApi();

    renderApp();

    expect(await screen.findByText("Base de datos")).toBeInTheDocument();
  });

  it("advierte cuando la API funciona en memoria", async () => {
    stubApi({ health: { ...HEALTH, persistence: "memory" } });

    renderApp();

    expect(await screen.findByText("Modo memoria")).toBeInTheDocument();
  });

  it("explica el vacío en lugar de mostrar una tabla sin filas", async () => {
    stubApi({ opportunities: page([]) });

    renderApp();

    expect(
      await screen.findByText("No hay oportunidades que mostrar."),
    ).toBeInTheDocument();
  });

  it("explica el fallo de la API sin dejar la pantalla en blanco", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        String(input).includes("/api/v1/auth/session")
          ? Promise.resolve(
              new Response(JSON.stringify(SESSION), { status: 200 }),
            )
          : Promise.resolve(new Response("{}", { status: 500 })),
      ),
    );

    renderApp();

    expect(
      await screen.findByText("No fue posible consultar las oportunidades."),
    ).toBeInTheDocument();
  });

  it("traduce el 503 a un mensaje sobre la persistencia", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        String(input).includes("/api/v1/auth/session")
          ? Promise.resolve(new Response(JSON.stringify(SESSION), { status: 200 }))
          : Promise.resolve(new Response("{}", { status: 503 })),
      ),
    );

    renderApp();

    expect(
      await screen.findByText("La persistencia no está configurada en la API."),
    ).toBeInTheDocument();
  });
});

// --- Cobertura -------------------------------------------------------------

describe("cobertura declarada", () => {
  it("declara la cobertura parcial de SECOP I", async () => {
    stubApi();

    renderApp();

    expect(await screen.findByText("Cobertura parcial")).toBeInTheDocument();
    expect(screen.getByText("Cobertura incompleta en una fuente")).toBeInTheDocument();
  });

  it("advierte de que la relación entre plataformas no está establecida", async () => {
    stubApi();

    renderApp();

    await waitFor(() =>
      expect(
        screen.getByText(/no está establecida/i),
      ).toBeInTheDocument(),
    );
  });
});

// --- Valores desconocidos --------------------------------------------------

describe("valores desconocidos", () => {
  it("muestra un guion en lugar de celda vacía", async () => {
    // Regla del sistema de diseño: un dato desconocido no es cero.
    stubApi({
      opportunities: page([
        opportunity({ reference: null, modality: null, published_at: null }),
      ]),
    });

    renderApp();

    await screen.findByText("E.S.E. Hospital Local");
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });

  it("no presenta un importe ausente como cero", async () => {
    stubApi({ opportunities: page([opportunity({ amount: null })]) });

    renderApp();

    const table = await screen.findByRole("table");
    // El guion, nunca "$ 0": «no consta» y «vale cero» son hechos distintos.
    expect(within(table).queryByText(/^\$\s?0$/)).not.toBeInTheDocument();
    expect(within(table).getByText("—")).toBeInTheDocument();
  });
});

// --- Filtros ---------------------------------------------------------------

describe("filtros", () => {
  it("envía el filtro de plataforma a la API", async () => {
    const fetchMock = stubApi();
    const user = userEvent.setup();

    renderApp();
    await screen.findByText("E.S.E. Hospital Local");
    await user.selectOptions(screen.getByLabelText("Plataforma"), "SECOP_I");

    await waitFor(() => {
      const calls = fetchMock.mock.calls.map((call) => String(call[0]));
      expect(calls.some((url) => url.includes("platform=SECOP_I"))).toBe(true);
    });
  });

  it("envía la búsqueda libre a la API", async () => {
    const fetchMock = stubApi();
    const user = userEvent.setup();

    renderApp();
    await screen.findByText("E.S.E. Hospital Local");
    await user.type(screen.getByLabelText("Buscar"), "hospital");

    await waitFor(() => {
      const calls = fetchMock.mock.calls.map((call) => String(call[0]));
      expect(calls.some((url) => url.includes("q=hospital"))).toBe(true);
    });
  });

  it("no envía filtros vacíos como cadenas vacías", async () => {
    const fetchMock = stubApi();

    renderApp();
    await screen.findByText("E.S.E. Hospital Local");

    const listCall = fetchMock.mock.calls
      .map((call) => String(call[0]))
      .find((url) => url.includes("/api/v1/opportunities"));
    // Un filtro vacío enviado como `q=` haría que el servidor filtrara por
    // cadena vacía y devolviera un subconjunto equivocado.
    expect(listCall).not.toContain("q=");
    expect(listCall).not.toContain("platform=");
  });

  it("ofrece limpiar solo cuando hay filtros activos", async () => {
    stubApi();
    const user = userEvent.setup();

    renderApp();
    await screen.findByText("E.S.E. Hospital Local");

    expect(screen.getByRole("button", { name: "Limpiar" })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Plataforma"), "SECOP_I");
    expect(screen.getByRole("button", { name: /Limpiar/ })).toBeEnabled();
  });
});

// --- Sincronización --------------------------------------------------------

describe("sincronización", () => {
  it("informa el resultado de una sincronización con novedades", async () => {
    stubApi({
      sync: { ...SYNC_OK, records_seen: 3, records_created: 3, last_offset: 3 },
    });
    const user = userEvent.setup();

    renderApp();
    await screen.findByText("E.S.E. Hospital Local");
    await user.click(screen.getByRole("button", { name: "Sincronizar" }));

    expect(await screen.findByText(/3 oportunidades nuevas/)).toBeInTheDocument();
  });

  it("informa cuando no hubo novedades", async () => {
    stubApi({ sync: { ...SYNC_OK, records_created: 0, records_unchanged: 1 } });
    const user = userEvent.setup();

    renderApp();
    await screen.findByText("E.S.E. Hospital Local");
    await user.click(screen.getByRole("button", { name: "Sincronizar" }));

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

    renderApp();
    await screen.findByText("E.S.E. Hospital Local");
    await user.click(screen.getByRole("button", { name: "Sincronizar" }));

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("quota_exceeded");
    expect(status).toHaveTextContent("El catálogo no se modificó");
  });
});

// --- Paginación ------------------------------------------------------------

describe("paginación", () => {
  it("deshabilita «Anterior» en la primera página", async () => {
    stubApi({ opportunities: page([opportunity()], 40) });

    renderApp();
    await screen.findByText("E.S.E. Hospital Local");

    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeEnabled();
  });

  it("indica el rango visible sobre el total", async () => {
    stubApi({ opportunities: page([opportunity()], 40) });

    renderApp();

    expect(await screen.findByText("1–1 de 40")).toBeInTheDocument();
  });
});

// --- Detalle ---------------------------------------------------------------

describe("detalle", () => {
  it("muestra la procedencia y el valor con su etiqueta", async () => {
    stubApi();

    renderApp("/oportunidades/1");

    // La etiqueta del valor depende de la plataforma: `precio_base` y
    // `cuantia_proceso` no miden lo mismo y no se presentan como equivalentes.
    expect(await screen.findByText("Precio base")).toBeInTheDocument();
    expect(screen.getByText("p6dx-8zbt")).toBeInTheDocument();
    // La insignia de procedencia está en la cabecera; el nombre de la
    // plataforma puede aparecer además en el texto explicativo.
    expect(screen.getAllByText("SECOP II").length).toBeGreaterThanOrEqual(1);
  });

  it("etiqueta el valor de SECOP I con su propio nombre", async () => {
    stubApi({
      detail: opportunity({
        source_dataset: "f789-7hwg",
        platform: "SECOP_I",
        platform_label: "SECOP I",
        amount_label: "Cuantía del proceso",
      }),
    });

    renderApp("/oportunidades/1");

    expect(await screen.findByText("Cuantía del proceso")).toBeInTheDocument();
  });

  it("enlaza a la fuente oficial en otra pestaña", async () => {
    stubApi();

    renderApp("/oportunidades/1");

    const link = await screen.findByRole("link", {
      name: "Ver en la fuente oficial",
    });
    expect(link).toHaveAttribute("href", "https://community.secop.gov.co/x");
    // `noopener` impide que la página abierta manipule esta mediante
    // `window.opener`.
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("explica que la oportunidad no existe en lugar de fallar", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        String(input).includes("/api/v1/auth/session")
          ? Promise.resolve(new Response(JSON.stringify(SESSION), { status: 200 }))
          : Promise.resolve(new Response("{}", { status: 404 })),
      ),
    );

    renderApp("/oportunidades/999");

    expect(
      await screen.findByText("La oportunidad no existe en el catálogo."),
    ).toBeInTheDocument();
  });
});
