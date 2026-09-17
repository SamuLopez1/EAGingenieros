import type { Opportunity } from "../api/contracts";
import {
  UNKNOWN,
  formatDate,
  formatText,
  isUnknown,
  staleness,
} from "../design/format";

/**
 * Tabla de oportunidades.
 *
 * Superficie de trabajo del analista. Decisiones del sistema de diseño que se
 * aplican aquí:
 *
 * - Solo hairlines horizontales. Las reglas verticales añaden ruido sin ayudar
 *   a recorrer la tabla; la alineación de columnas ya guía la vista.
 * - Cifras tabulares en fecha e identificador, para que las columnas alineen.
 * - Valores desconocidos como guion atenuado, nunca como celda vacía.
 * - El título y la entidad no se truncan sin salida: dos procesos de la misma
 *   entidad son frecuentes y un nombre cortado provoca lecturas equivocadas.
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
  selectedId,
  onSelect,
}: {
  items: Opportunity[];
  selectedId?: number | null;
  onSelect?: (opportunity: Opportunity) => void;
}) {
  if (items.length === 0) {
    return (
      <div className="empty">
        <p className="empty-title">No hay oportunidades sincronizadas.</p>
        <p className="empty-hint">
          Ejecute una sincronización para incorporar procesos desde SECOP II.
        </p>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table className="dense">
        <caption className="sr-only">
          Oportunidades sincronizadas desde SECOP II
        </caption>
        <thead>
          <tr>
            <th scope="col">Entidad y proceso</th>
            <th scope="col">Referencia</th>
            <th scope="col">Modalidad</th>
            <th scope="col">Publicación</th>
            <th scope="col">Estado SECOP</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const selected = selectedId === item.id;
            return (
              <tr
                key={item.id}
                className={selected ? "is-selected" : undefined}
                onClick={onSelect ? () => onSelect(item) : undefined}
                // La fila entera es pulsable, pero también debe poder recorrerse
                // con teclado sin depender del ratón.
                tabIndex={onSelect ? 0 : undefined}
                onKeyDown={
                  onSelect
                    ? (event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          onSelect(item);
                        }
                      }
                    : undefined
                }
                aria-selected={onSelect ? selected : undefined}
              >
                <td>
                  <div className="cell-entity">{formatText(item.entity)}</div>
                  <div className="cell-title">{formatText(item.title)}</div>
                </td>
                <Cell value={item.reference} className="tnum" />
                <Cell value={item.modality} />
                <Cell value={formatDate(item.published_at)} className="tnum" />
                <Cell value={item.status} />
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Aviso de antigüedad del catálogo.
 *
 * Una tabla desactualizada parece completa. Declararlo evita que el analista
 * decida sobre un catálogo que ya no refleja SECOP.
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
