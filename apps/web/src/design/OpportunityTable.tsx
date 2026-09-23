import { Link } from "react-router-dom";

import type { Opportunity } from "../api/contracts";
import {
  UNKNOWN,
  formatAmount,
  formatDate,
  formatText,
  isUnknown,
  staleness,
} from "../design/format";
import { DuplicateNotice, SourceBadge } from "./Provenance";

/**
 * Tabla de oportunidades.
 *
 * Superficie de trabajo del analista. Decisiones del sistema de diseño que se
 * aplican aquí:
 *
 * - Solo hairlines horizontales. Las reglas verticales añaden ruido sin ayudar
 *   a recorrer la tabla; la alineación de columnas ya guía la vista.
 * - Cifras tabulares en fecha, referencia y valor, para que las columnas
 *   alineen y un dígito no se lea en la fila equivocada.
 * - Valores desconocidos como guion atenuado, nunca como celda vacía ni como
 *   cero: en este dominio «no consta» y «vale cero» son hechos distintos.
 * - El título y la entidad no se truncan sin salida: dos procesos de la misma
 *   entidad son frecuentes y un nombre cortado provoca lecturas equivocadas.
 * - La procedencia va en cada fila. Al mezclar dos plataformas en una tabla, un
 *   encabezado que diga «SECOP» no basta: hay que saber de cuál viene cada una.
 */

function Cell({
  value,
  className = "",
}: {
  value: string | null;
  className?: string;
}) {
  const unknown = isUnknown(value);
  return (
    <td className={`${className}${unknown ? " is-unknown" : ""}`.trim()}>
      {unknown ? UNKNOWN : value}
    </td>
  );
}

export function OpportunityTable({
  items,
  emptyHint = "Ejecute una sincronización para incorporar procesos de las fuentes registradas.",
}: {
  items: Opportunity[];
  emptyHint?: string;
}) {
  if (items.length === 0) {
    return (
      <div className="empty">
        <p className="empty-title">No hay oportunidades que mostrar.</p>
        <p className="empty-hint">{emptyHint}</p>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table className="dense">
        <caption className="sr-only">
          Oportunidades sincronizadas desde SECOP I y SECOP II, con su
          procedencia y su valor económico
        </caption>
        <thead>
          <tr>
            <th scope="col">Fuente</th>
            <th scope="col">Entidad y proceso</th>
            <th scope="col">Referencia</th>
            <th scope="col">Modalidad</th>
            <th scope="col">Publicación</th>
            <th scope="col" className="num">
              Valor
            </th>
            <th scope="col">Estado SECOP</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td className="cell-source">
                <SourceBadge platform={item.platform} label={item.platform_label} />
              </td>
              <td>
                {/* El enlace es el control accesible: tiene `href`, se puede
                    abrir en otra pestaña y se recorre con el teclado. La fila
                    entera no se hace pulsable para no duplicar el destino ni
                    romper la selección de texto. */}
                <Link className="cell-link" to={`/oportunidades/${item.id}`}>
                  <span className="cell-entity">{formatText(item.entity)}</span>
                  <span className="cell-title">{formatText(item.title)}</span>
                </Link>
                {item.possible_duplicate ? (
                  <DuplicateNotice platforms={item.duplicate_platforms} />
                ) : null}
              </td>
              <Cell value={item.reference} className="tnum" />
              <Cell value={item.modality} />
              <Cell value={formatDate(item.published_at)} className="tnum" />
              <td className="num tnum">
                {/* La etiqueta del valor acompaña al número porque `precio_base`
                    y `cuantia_proceso` no miden lo mismo: presentarlos bajo una
                    etiqueta común afirmaría una equivalencia inexistente. */}
                <span
                  className={item.amount === null ? "is-unknown" : undefined}
                  title={item.amount_label}
                >
                  {formatAmount(item.amount)}
                </span>
              </td>
              <Cell value={item.status} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Aviso de antigüedad del catálogo.
 *
 * Una tabla desactualizada parece completa. Declararlo evita que el analista
 * decida sobre un catálogo que ya no refleja las fuentes.
 */
export function StalenessNotice({
  lastSyncedAt,
}: {
  lastSyncedAt: string | null | undefined;
}) {
  const { label, stale } = staleness(lastSyncedAt);
  return (
    <p className={stale ? "stale is-stale" : "stale"}>
      Última sincronización: <span className="tnum">{label}</span>
      {stale ? " · los datos pueden estar desactualizados" : null}
    </p>
  );
}
