/**
 * Listado de oportunidades.
 *
 * El estado de los filtros vive en la dirección, no en el componente. Es una
 * decisión, no una preferencia: MVP-06 exige que el detalle permita «volver al
 * listado sin perder filtros», y eso solo funciona si los filtros forman parte
 * de la ubicación. Además hace que el listado se pueda compartir por enlace y
 * que el botón «atrás» del navegador haga lo que se espera.
 *
 * Los filtros se leen de la URL en cada render, así que una navegación hacia
 * atrás los restaura sin código adicional.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  ApiError,
  fetchOpportunities,
  fetchSources,
  triggerSync,
} from "../api/client";
import type { OpportunityFilters, Platform } from "../api/contracts";
import { CoverageBanner } from "../design/CoverageBanner";
import { FilterBar } from "../design/FilterBar";
import { OpportunityTable, StalenessNotice } from "../design/OpportunityTable";
import { useDebounced } from "../design/useDebounced";

const PAGE_SIZE = 25;

/** Claves de la dirección que son filtros. Se listan para poder limpiarlas. */
const FILTER_KEYS = [
  "q",
  "platform",
  "source",
  "estado",
  "modalidad",
  "entity_nit",
  "desde",
  "hasta",
] as const;

function filtersFrom(params: URLSearchParams): OpportunityFilters {
  const filters: OpportunityFilters = {};
  for (const key of FILTER_KEYS) {
    const value = params.get(key);
    if (value) {
      // `platform` y `source` tienen tipo propio; el resto son cadenas.
      if (key === "platform") filters.platform = value as Platform;
      else if (key === "source") filters.source = value;
      else filters[key] = value;
    }
  }
  return filters;
}

export function OpportunitiesPage() {
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();

  const filters = useMemo(() => filtersFrom(params), [params]);
  const offset = Number(params.get("offset") ?? "0") || 0;
  const activeCount = Object.keys(filters).length;
  // Solo la consulta espera; el campo de texto se actualiza al instante.
  const queryFilters = useDebounced(filters, 300);

  const opportunities = useQuery({
    queryKey: ["opportunities", queryFilters, offset],
    queryFn: ({ signal }) =>
      fetchOpportunities(
        { filters: queryFilters, limit: PAGE_SIZE, offset },
        signal,
      ),
  });

  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: ({ signal }) => fetchSources(signal),
    // La cobertura cambia solo al sincronizar, así que no hace falta
    // refrescarla en cada vuelta a la página.
    staleTime: 60_000,
  });

  const sync = useMutation({
    mutationFn: (dataset?: string) => triggerSync({ dataset, limit: 50 }),
    onSuccess: async () => {
      // Se invalida todo lo afectado: el listado, la cobertura y el historial.
      await queryClient.invalidateQueries({ queryKey: ["opportunities"] });
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      await queryClient.invalidateQueries({ queryKey: ["sync-runs"] });
    },
  });

  const updateFilters = useCallback(
    (patch: Partial<OpportunityFilters>) => {
      const next = new URLSearchParams(params);
      for (const [key, value] of Object.entries(patch)) {
        if (value === undefined || value === "") next.delete(key);
        else next.set(key, String(value));
      }
      // Cambiar un filtro invalida la página actual: quedarse en el offset 75
      // de un resultado que ahora tiene 3 filas mostraría una tabla vacía sin
      // explicar por qué.
      next.delete("offset");
      setParams(next, { replace: true });
    },
    [params, setParams],
  );

  const clearFilters = useCallback(() => {
    setParams(new URLSearchParams(), { replace: true });
  }, [setParams]);

  const goToOffset = useCallback(
    (next: number) => {
      const updated = new URLSearchParams(params);
      if (next <= 0) updated.delete("offset");
      else updated.set("offset", String(next));
      setParams(updated);
    },
    [params, setParams],
  );

  const page = opportunities.data;
  // La antigüedad se toma del dato más reciente sincronizado de la página.
  const lastSyncedAt = page?.items[0]?.last_synced_at ?? null;
  const hasPrev = offset > 0;
  const hasNext = page ? offset + page.items.length < page.total : false;

  return (
    <main className="wrap">
      <section className="head">
        <div>
          <h1>Oportunidades</h1>
          <p className="lead">
            Procesos incorporados desde las fuentes registradas. La decisión de
            participar permanece en manos del analista.
          </p>
        </div>
        <div className="head-actions">
          <button
            type="button"
            className="btn btn-p"
            onClick={() => sync.mutate(undefined)}
            disabled={sync.isPending}
          >
            {sync.isPending ? "Sincronizando…" : "Sincronizar"}
          </button>
          <Link className="btn btn-s" to="/fuentes">
            Fuentes
          </Link>
        </div>
      </section>

      {sync.isSuccess ? (
        <div className="banner banner-ok" role="status">
          {sync.data.outcome === "completed"
            ? sync.data.records_created > 0
              ? `${sync.data.records_created} oportunidades nuevas, ${sync.data.records_unchanged} sin cambios.`
              : `Sin novedades: ${sync.data.records_unchanged} oportunidades ya estaban al día.`
            : `La sincronización falló (${sync.data.error_kind ?? "error"}). El catálogo no se modificó.`}
        </div>
      ) : null}

      {sync.isError ? (
        <div className="banner banner-warn" role="alert">
          No fue posible ejecutar la sincronización. El catálogo no se modificó.
        </div>
      ) : null}

      {sources.data ? <CoverageBanner sources={sources.data.sources} /> : null}

      <FilterBar
        filters={filters}
        onChange={updateFilters}
        onClear={clearFilters}
        activeCount={activeCount}
      />

      {page && page.items.length > 0 ? (
        <StalenessNotice lastSyncedAt={lastSyncedAt} />
      ) : null}

      <section className="panel">
        {opportunities.isPending ? (
          <div className="empty">
            <p className="empty-title">Cargando oportunidades…</p>
          </div>
        ) : null}

        {opportunities.isError ? (
          <div className="empty">
            <p className="empty-title">
              {describeLoadError(opportunities.error)}
            </p>
            <p className="empty-hint">
              {opportunities.error instanceof ApiError &&
              opportunities.error.isUnauthorized
                ? "Vuelva a iniciar sesión para continuar."
                : "Compruebe que la API esté en ejecución y accesible."}
            </p>
          </div>
        ) : null}

        {page ? (
          <OpportunityTable
            items={page.items}
            emptyHint={
              activeCount > 0
                ? "Ningún proceso coincide con los filtros aplicados. Quite algún filtro para ampliar la búsqueda."
                : "Ejecute una sincronización para incorporar procesos de las fuentes registradas."
            }
          />
        ) : null}
      </section>

      {page && page.total > 0 ? (
        <nav className="pager" aria-label="Paginación">
          <span className="pager-info tnum">
            {offset + 1}–{offset + page.items.length} de {page.total}
          </span>
          <div className="pager-actions">
            <button
              type="button"
              className="btn btn-s"
              onClick={() => goToOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={!hasPrev}
            >
              Anterior
            </button>
            <button
              type="button"
              className="btn btn-s"
              onClick={() => goToOffset(offset + PAGE_SIZE)}
              disabled={!hasNext}
            >
              Siguiente
            </button>
          </div>
        </nav>
      ) : null}
    </main>
  );
}

function describeLoadError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.isForbidden) return "Su cuenta no tiene permiso para ver el catálogo.";
    if (error.isUnauthorized) return "La sesión no es válida.";
    if (error.isUnavailable) return "La persistencia no está configurada en la API.";
    if (error.status === 400) return error.detail ?? "Los filtros enviados no son válidos.";
  }
  return "No fue posible consultar las oportunidades.";
}
