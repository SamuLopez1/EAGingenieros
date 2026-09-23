/**
 * Página de fuentes.
 *
 * Existe para que la cobertura sea consultable y no una frase escondida en un
 * pie de página. También permite sincronizar una fuente concreta: cuando algo
 * falta, el analista necesita poder pedir esa fuente y no una sincronización
 * genérica que quizá no la incluya.
 *
 * Se muestra el historial de ejecuciones porque una sincronización que falla
 * en silencio es indistinguible de una que no trajo novedades. Aquí se ve cuál
 * falló, cuándo y por qué tipo de error.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchSources, fetchSyncRuns, triggerSync } from "../api/client";
import { coverageLabel, coverageNeedsWarning, PLATFORM_MEANINGS } from "../design/platform";
import { formatDateTime, formatText, UNKNOWN } from "../design/format";

export function SourcesPage() {
  const queryClient = useQueryClient();

  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: ({ signal }) => fetchSources(signal),
  });

  const runs = useQuery({
    queryKey: ["sync-runs"],
    queryFn: ({ signal }) => fetchSyncRuns({ limit: 15 }, signal),
  });

  const sync = useMutation({
    mutationFn: (dataset: string) => triggerSync({ dataset, limit: 50 }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      await queryClient.invalidateQueries({ queryKey: ["sync-runs"] });
      await queryClient.invalidateQueries({ queryKey: ["opportunities"] });
    },
  });

  return (
    <main className="wrap">
      <div className="detail-actions">
        <Link className="btn btn-s" to="/">
          ← Volver al listado
        </Link>
      </div>

      <section className="head">
        <div>
          <h1>Fuentes</h1>
          <p className="lead">
            Qué se sincroniza y qué no. Lo que no está cubierto se declara: el
            listado no debe dar a entender que contiene todo el mercado público.
          </p>
        </div>
      </section>

      {sync.isSuccess ? (
        <div
          className={
            sync.data.outcome === "completed" ? "banner banner-ok" : "banner banner-warn"
          }
          role="status"
        >
          {sync.data.outcome === "completed"
            ? `${sync.data.records_created} nuevas, ${sync.data.records_updated} actualizadas, ${sync.data.records_unchanged} sin cambios.`
            : `La sincronización falló (${sync.data.error_kind ?? "error"}). El catálogo no se modificó.`}
        </div>
      ) : null}

      <section className="panel detail-panel">
        <h2 className="detail-section">Cobertura declarada</h2>

        {sources.isPending ? <p className="detail-note">Consultando fuentes…</p> : null}
        {sources.isError ? (
          <p className="detail-note">
            No fue posible consultar las fuentes. Compruebe que la API responda.
          </p>
        ) : null}

        {sources.data ? (
          <ul className="source-cards">
            {sources.data.sources.map((source) => (
              <li key={source.dataset} className="source-card">
                <div className="source-card-head">
                  <strong>{source.short_label}</strong>
                  <span
                    className={
                      coverageNeedsWarning(source.coverage)
                        ? "coverage-state is-warn"
                        : "coverage-state"
                    }
                  >
                    {coverageLabel(source.coverage)}
                  </span>
                </div>
                <p className="source-card-label">{source.label}</p>
                <p className="source-card-note">{source.note}</p>
                <div className="source-card-meta">
                  <span className="tnum">
                    {source.opportunity_count.toLocaleString("es-CO")} oportunidades
                  </span>
                  <span className="tnum source-dataset">{source.dataset}</span>
                </div>
                <p className="source-card-note source-card-quirk">
                  Valor económico: <strong>{source.amount_label}</strong>. No es
                  comparable con el de la otra plataforma.
                </p>
                <p className="source-card-note">{PLATFORM_MEANINGS[source.platform]}</p>
                <button
                  type="button"
                  className="btn btn-s"
                  onClick={() => sync.mutate(source.dataset)}
                  disabled={sync.isPending}
                >
                  {sync.isPending && sync.variables === source.dataset
                    ? "Sincronizando…"
                    : `Sincronizar ${source.short_label}`}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="panel detail-panel">
        <h2 className="detail-section">Últimas sincronizaciones</h2>

        {runs.isPending ? <p className="detail-note">Consultando historial…</p> : null}
        {runs.data && runs.data.length === 0 ? (
          <p className="detail-note">
            Todavía no se ha ejecutado ninguna sincronización.
          </p>
        ) : null}

        {runs.data && runs.data.length > 0 ? (
          <div className="table-wrap">
            <table className="dense">
              <caption className="sr-only">
                Historial de sincronizaciones por fuente
              </caption>
              <thead>
                <tr>
                  <th scope="col">Inicio</th>
                  <th scope="col">Fuente</th>
                  <th scope="col">Resultado</th>
                  <th scope="col" className="num">
                    Nuevas
                  </th>
                  <th scope="col" className="num">
                    Actualizadas
                  </th>
                  <th scope="col">Error</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.map((run) => (
                  <tr key={run.id}>
                    <td className="tnum">{formatDateTime(run.started_at)}</td>
                    <td className="tnum">{run.dataset}</td>
                    <td>
                      <span
                        className={
                          run.outcome === "completed"
                            ? "run-outcome is-ok"
                            : run.outcome === "running"
                              ? "run-outcome"
                              : "run-outcome is-bad"
                        }
                      >
                        {run.outcome === "completed"
                          ? "Completada"
                          : run.outcome === "running"
                            ? "En curso"
                            : "Fallida"}
                      </span>
                    </td>
                    <td className="num tnum">{run.records_created}</td>
                    <td className="num tnum">{run.records_updated}</td>
                    <td>{run.error_kind ? formatText(run.error_kind) : UNKNOWN}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </main>
  );
}
