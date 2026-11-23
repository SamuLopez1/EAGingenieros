import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CatalogFreshness } from "./CatalogFreshness";
import { catalogWarning } from "./catalogAge";
import { formatColombiaDateTime } from "./format";
import type { OpportunityPage } from "../api/contracts";

const now = Date.parse("2026-10-15T12:00:00Z");
const page: OpportunityPage = {
  items: [],
  total: 0,
  limit: 25,
  offset: 0,
  latest_sync_outcome: "completed",
  catalog_synced_at: "2026-10-14T12:00:00Z",
  catalog_stale_after_hours: 24,
};
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

it("distingue nunca sincronizado, fallo y ejecución en curso aunque haya una carga reciente", () => {
  expect(
    catalogWarning({ ...page, latest_sync_outcome: null, catalog_synced_at: null }, now),
  ).toMatch(/nunca sincronizado/);
  expect(
    catalogWarning(
      { ...page, latest_sync_outcome: "failed", catalog_synced_at: new Date(now).toISOString() },
      now,
    ),
  ).toMatch(/falló/);
  expect(
    catalogWarning({ ...page, latest_sync_outcome: "running", catalog_synced_at: null }, now),
  ).toMatch(/en curso/);
  expect(catalogWarning({ ...page, latest_sync_outcome: "interrupted" }, now)).toMatch(
    /No hay una sincronización completa/,
  );
});

it("usa catalog_synced_at, instantes con offset y el límite inclusivo del umbral configurado", () => {
  expect(catalogWarning(page, now - 1)).toBeNull();
  expect(catalogWarning(page, now)).toMatch(/correcta.*al menos 24 horas/);
  expect(catalogWarning(page, now + 1)).toMatch(/desactualizados/);
  expect(catalogWarning({ ...page, catalog_synced_at: "2026-10-14T07:00:00-05:00" }, now)).toEqual(
    catalogWarning(page, now),
  );
  expect(catalogWarning({ ...page, catalog_stale_after_hours: 48 }, now)).toBeNull();
  expect(catalogWarning({ ...page, catalog_stale_after_hours: 1 }, now)).toMatch(/1 horas/);
  expect(catalogWarning({ ...page, catalog_synced_at: null }, now)).toMatch(/sin fecha de carga/);
});

it("actualiza el aviso con reloj controlado sin recargar la página y limpia el temporizador", () => {
  vi.useFakeTimers();
  vi.setSystemTime(now - 30_000);
  const view = render(<CatalogFreshness page={page} />);
  expect(screen.queryByText(/al menos 24 horas/)).not.toBeInTheDocument();
  act(() => {
    vi.advanceTimersByTime(30_000);
  });
  expect(screen.getByText(/al menos 24 horas/)).toBeInTheDocument();
  expect(screen.getByText(/provisional.*validación con EAG/)).toBeInTheDocument();
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
});

it("muestra horas de carga en Colombia aunque el navegador use otra zona, conservando el instante", () => {
  expect(formatColombiaDateTime("2026-10-15T02:30:00Z")).toBe("14/10/2026, 21:30");
  expect(formatColombiaDateTime("2026-10-14T21:30:00-05:00")).toBe("14/10/2026, 21:30");
  expect(formatColombiaDateTime(null)).toBe("—");
  render(<CatalogFreshness page={{ ...page, latest_sync_finished_at: "2026-10-15T02:30:00Z" }} />);
  expect(
    screen.getByText(/Última sincronización finalizada.*14\/10\/2026, 21:30/),
  ).toBeInTheDocument();
});
