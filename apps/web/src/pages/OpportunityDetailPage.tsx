/**
 * Detalle de una oportunidad.
 *
 * Muestra la procedencia completa, el valor con su etiqueta de origen y los
 * datos tal como llegaron. El enlace a la fuente oficial se abre en otra
 * pestaña: el analista necesita comprobar el dato sin perder el contexto de la
 * aplicación.
 *
 * Las fechas se muestran con hora además de con día. En una licitación, el
 * plazo se decide por horas, y una fecha sin hora obliga a ir al sitio oficial
 * para algo que el sistema ya sabe.
 */

import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, fetchOpportunity } from "../api/client";
import { DuplicateNotice, SourceBadge } from "../design/Provenance";
import { formatAmount, formatDateTime, formatText, UNKNOWN } from "../design/format";
import { COVERAGE_MEANINGS } from "../design/platform";

export function OpportunityDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const numericId = Number(id);

  const opportunity = useQuery({
    queryKey: ["opportunity", numericId],
    queryFn: ({ signal }) => fetchOpportunity(numericId, signal),
    enabled: Number.isFinite(numericId) && numericId > 0,
    retry: (count, error) =>
      // Un 404 no se reintenta: reintentarlo solo retrasa el mensaje.
      !(error instanceof ApiError && error.status === 404) && count < 2,
  });

  const goBack = () => {
    // `-1` devuelve a la dirección anterior con sus filtros intactos, que es
    // justo lo que MVP-06 exige. Si no hay historial, se vuelve al listado.
    if (window.history.length > 1) navigate(-1);
    else navigate("/");
  };

  if (opportunity.isPending) {
    return (
      <main className="wrap">
        <div className="empty">
          <p className="empty-title">Cargando la oportunidad…</p>
        </div>
      </main>
    );
  }

  if (opportunity.isError) {
    const error = opportunity.error;
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <main className="wrap">
        <div className="empty">
          <p className="empty-title">
            {notFound
              ? "La oportunidad no existe en el catálogo."
              : "No fue posible consultar la oportunidad."}
          </p>
          <p className="empty-hint">
            {notFound
              ? "Puede haber sido eliminada por la política de retención."
              : "Compruebe que la API esté en ejecución y accesible."}
          </p>
        </div>
        <div className="detail-actions">
          <button type="button" className="btn btn-s" onClick={goBack}>
            Volver al listado
          </button>
        </div>
      </main>
    );
  }

  const item = opportunity.data;
  // La plataforma decide qué se declara sobre la cobertura de este registro.
  const coverageKey = item.platform === "SECOP_I" ? "parcial" : "sincronizada";

  return (
    <main className="wrap">
      <div className="detail-actions">
        <button type="button" className="btn btn-s" onClick={goBack}>
          ← Volver al listado
        </button>
      </div>

      <section className="head">
        <div>
          <div className="detail-provenance">
            <SourceBadge platform={item.platform} label={item.platform_label} />
            <span className="detail-dataset tnum">{item.source_dataset}</span>
            {item.possible_duplicate ? (
              <DuplicateNotice platforms={item.duplicate_platforms} />
            ) : null}
          </div>
          <h1 className="detail-title">{formatText(item.title)}</h1>
          <p className="lead">{formatText(item.entity)}</p>
        </div>
        {item.official_url ? (
          <div className="head-actions">
            <a
              className="btn btn-p"
              href={item.official_url}
              target="_blank"
              rel="noreferrer noopener"
            >
              Ver en la fuente oficial
            </a>
          </div>
        ) : null}
      </section>

      {item.possible_duplicate ? (
        <div className="banner banner-warn" role="status">
          El mismo NIT y la misma referencia aparecen en{" "}
          {item.duplicate_platforms.join(" y ")}. Puede ser el mismo proceso
          publicado en dos plataformas, o dos procesos distintos con
          referencias coincidentes. <strong>El sistema no los fusiona:</strong>{" "}
          compruébelo antes de decidir.
        </div>
      ) : null}

      <section className="panel detail-panel">
        <dl className="detail-grid">
          <Field label="Referencia" value={item.reference} tabular />
          <Field label="Identificador de origen" value={item.source_id} tabular />
          <Field label="NIT de la entidad" value={item.entity_nit} tabular />
          <Field label="Estado SECOP" value={item.status} />
          <Field label="Modalidad" value={item.modality} />
          <Field label="Publicación" value={formatDateTime(item.published_at)} tabular />
          <Field
            label="Última actualización en la fuente"
            value={formatDateTime(item.last_updated_at)}
            tabular
          />
          {/* El valor lleva su etiqueta de origen. `precio_base` y
              `cuantia_proceso` no miden lo mismo, así que no se presenta bajo
              una etiqueta genérica de «valor». */}
          <Field
            label={item.amount_label || "Valor"}
            value={item.amount === null ? UNKNOWN : formatAmount(item.amount)}
            tabular
            muted={item.amount === null}
          />
          <Field label="Primera vez visto" value={formatDateTime(item.first_seen_at)} tabular />
          <Field
            label="Última sincronización"
            value={formatDateTime(item.last_synced_at)}
            tabular
          />
        </dl>
      </section>

      <section className="panel detail-panel">
        <h2 className="detail-section">Procedencia</h2>
        {/* El identificador del conjunto y la plataforma ya están en la
            cabecera. La declaración de cobertura vive en el listado y en la
            página de fuentes: repetirla aquí llenaba el detalle de texto que el
            analista ya leyó antes de entrar. */}
        <p className="detail-note">{COVERAGE_MEANINGS[coverageKey]}</p>
        <p className="detail-note">
          Los datos se conservan tal como los publicó la fuente, incluidos los
          campos que esta aplicación todavía no muestra. Eso permite corregir la
          normalización más adelante sin volver a consultar el origen.
        </p>
      </section>
    </main>
  );
}

function Field({
  label,
  value,
  tabular = false,
  muted = false,
}: {
  label: string;
  value: string | null | undefined;
  tabular?: boolean;
  muted?: boolean;
}) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div className="detail-field">
      <dt>{label}</dt>
      <dd
        className={`${tabular ? "tnum" : ""}${empty || muted ? " is-unknown" : ""}`.trim()}
      >
        {empty ? UNKNOWN : value}
      </dd>
    </div>
  );
}
