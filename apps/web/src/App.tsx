import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  fetchHealth,
  fetchOpportunities,
  triggerSync,
} from "./api/client";
import type { Health, Opportunity, OpportunityPage } from "./api/contracts";
import { OpportunityTable, StalenessNotice } from "./design/OpportunityTable";
import "./design/tokens.css";
import "./design/app.css";

const PAGE_SIZE = 25;

type Load =
  | { kind: "loading" }
  | { kind: "ready"; page: OpportunityPage }
  | { kind: "error"; message: string };

type SyncState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "done"; message: string }
  | { kind: "failed"; message: string };

export function App() {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [health, setHealth] = useState<Health | null>(null);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Opportunity | null>(null);
  const [sync, setSync] = useState<SyncState>({ kind: "idle" });

  const loadPage = useCallback(
    async (requestedOffset: number, signal?: AbortSignal) => {
      try {
        const page = await fetchOpportunities(
          { limit: PAGE_SIZE, offset: requestedOffset },
          signal,
        );
        if (signal?.aborted) return;
        setLoad({ kind: "ready", page });
      } catch (error) {
        if (signal?.aborted) return;
        setLoad({
          kind: "error",
          message:
            error instanceof ApiError && error.status === 503
              ? "La persistencia no está configurada en la API."
              : "No fue posible consultar las oportunidades.",
        });
      }
    },
    [],
  );

  // La consulta se hace dentro del efecto porque es una suscripción a un
  // recurso externo: el resultado se descarta si el componente se desmonta o si
  // el offset cambió antes de que responda. `loadPage` se invoca desde aquí y
  // desde el manejador de sincronización, de modo que no hay dos caminos que
  // puedan dejar el estado desincronizado.
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    fetchOpportunities({ limit: PAGE_SIZE, offset }, controller.signal)
      .then((page) => {
        if (active) setLoad({ kind: "ready", page });
      })
      .catch((error: unknown) => {
        if (!active) return;
        setLoad({
          kind: "error",
          message:
            error instanceof ApiError && error.status === 503
              ? "La persistencia no está configurada en la API."
              : "No fue posible consultar las oportunidades.",
        });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [offset]);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then(setHealth)
      .catch(() => {
        if (!controller.signal.aborted) setHealth(null);
      });
    return () => controller.abort();
  }, []);

  const onSync = useCallback(async () => {
    setSync({ kind: "running" });
    try {
      const result = await triggerSync({ limit: 50 });
      if (result.outcome === "completed") {
        setSync({
          kind: "done",
          message:
            result.records_created > 0
              ? `${result.records_created} oportunidades nuevas, ${result.records_unchanged} sin cambios.`
              : `Sin novedades: ${result.records_unchanged} oportunidades ya estaban al día.`,
        });
      } else {
        setSync({
          kind: "failed",
          message: `La sincronización falló (${result.error_kind ?? "error"}).`,
        });
      }
      setOffset(0);
      await loadPage(0);
    } catch {
      setSync({
        kind: "failed",
        message: "No fue posible ejecutar la sincronización.",
      });
    }
  }, [loadPage]);

  const page = load.kind === "ready" ? load.page : null;
  const lastSyncedAt = page?.items[0]?.last_synced_at ?? null;
  const hasPrev = offset > 0;
  const hasNext = page ? offset + page.items.length < page.total : false;

  return (
    <>
      <header className="top">
        <div className="wrap top-in">
          <div className="brand">
            <span className="mark" aria-hidden="true" />
            EAG · Licitaciones
          </div>
          <div className="top-right">
            {health ? (
              <span
                className={
                  health.persistence === "database"
                    ? "env env-db"
                    : "env env-mem"
                }
                title={
                  health.persistence === "database"
                    ? "Los datos se conservan en base de datos."
                    : "Modo memoria: los datos se pierden al reiniciar."
                }
              >
                {health.persistence === "database"
                  ? "Base de datos"
                  : "Modo memoria"}
              </span>
            ) : null}
          </div>
        </div>
      </header>

      <main className="wrap">
        <section className="head">
          <div>
            <h1>Oportunidades</h1>
            <p className="lead">
              Procesos incorporados desde SECOP II. La decisión de participar
              permanece en manos del analista.
            </p>
          </div>
          <div className="head-actions">
            <button
              type="button"
              className="btn btn-p"
              onClick={() => void onSync()}
              disabled={sync.kind === "running"}
            >
              {sync.kind === "running" ? "Sincronizando…" : "Sincronizar ahora"}
            </button>
          </div>
        </section>

        {sync.kind === "done" ? (
          <div className="banner banner-ok" role="status">
            {sync.message}
          </div>
        ) : null}
        {sync.kind === "failed" ? (
          <div className="banner banner-warn" role="alert">
            {sync.message} El catálogo no se modificó.
          </div>
        ) : null}

        {page && page.items.length > 0 ? (
          <StalenessNotice lastSyncedAt={lastSyncedAt} />
        ) : null}

        <section className="panel">
          {load.kind === "loading" ? (
            <div className="empty">
              <p className="empty-title">Cargando oportunidades…</p>
            </div>
          ) : null}

          {load.kind === "error" ? (
            <div className="empty">
              <p className="empty-title">{load.message}</p>
              <p className="empty-hint">
                Compruebe que la API esté en ejecución y accesible.
              </p>
            </div>
          ) : null}

          {page ? (
            <OpportunityTable
              items={page.items}
              selectedId={selected?.id ?? null}
              onSelect={setSelected}
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
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                disabled={!hasPrev}
              >
                Anterior
              </button>
              <button
                type="button"
                className="btn btn-s"
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={!hasNext}
              >
                Siguiente
              </button>
            </div>
          </nav>
        ) : null}

        <p className="footnote">
          Datos oficiales de SECOP II. La relación entre el conjunto de procesos
          y el de archivos no está confirmada: los documentos complementarios se
          cargan manualmente.
        </p>
      </main>
    </>
  );
}
