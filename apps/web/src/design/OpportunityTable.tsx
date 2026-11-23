import type { Opportunity } from "../api/contracts";
import { formatDate, formatText } from "./format";
import { validityLabels } from "./validity";

export function OpportunityTable({
  items,
  detailHref,
  onOpen,
}: {
  items: Opportunity[];
  detailHref: (id: number) => string;
  onOpen: (id: number) => void;
}) {
  return (
    <div className="table-wrap" role="region" aria-label="Resultados del catálogo" tabIndex={0}>
      <table className="dense">
        <caption className="sr-only">Oportunidades sincronizadas desde SECOP II</caption>
        <thead>
          <tr>
            <th scope="col">Entidad y proceso</th>
            <th scope="col">Referencia</th>
            <th scope="col">Modalidad</th>
            <th scope="col">Cierre (UTC)</th>
            <th scope="col">Estado SECOP</th>
            <th scope="col">Vigencia</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>
                <div className="cell-entity">{formatText(item.entity)}</div>
                <div className="cell-title">
                  <a id={`opportunity-${item.id}`} href={detailHref(item.id)} onClick={(event) => {
                    if (event.button === 0 && !event.metaKey && !event.ctrlKey &&
                        !event.shiftKey && !event.altKey) {
                      event.preventDefault();
                      onOpen(item.id);
                    }
                  }}>{formatText(item.title)}</a>
                </div>
                {item.city || item.department ? (
                  <small>{[item.city, item.department].filter(Boolean).join(", ")}</small>
                ) : null}
              </td>
              <td data-label="Referencia" className="tnum">{formatText(item.reference)}</td>
              <td data-label="Modalidad">{formatText(item.modality)}</td>
              <td data-label="Cierre (UTC)" className="tnum">{formatDate(item.reception_at)}</td>
              <td data-label="Estado SECOP">{formatText(item.status)}</td>
              <td data-label="Vigencia"><span className={`catalog-validity catalog-validity--${item.validity}`}>
                {validityLabels[item.validity]}
              </span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
