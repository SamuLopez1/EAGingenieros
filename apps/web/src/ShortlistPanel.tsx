import { useEffect, useState } from "react";
import type { MouseEvent } from "react";
import { outcomes } from "./api/comparison";
import { formatLocator } from "./api/extraction";
import { labels } from "./api/margin";
import type { Citation } from "./api/requirements";
import { fetchShortlistComparison } from "./api/shortlist";
import type { Column, ComparisonTable, SavedOpportunity } from "./api/shortlist";
import { formatDateTime } from "./design/format";
import type { useShortlist } from "./useShortlist";

type Navigation = { detailHref: (id: number) => string; onOpen: (id: number) => void };
type Selection = ReturnType<typeof useShortlist>;
const kindLabels = { habilitante: "Habilitante", evaluable: "Evaluable", obligacion: "Obligación" };

function opportunityName(item: SavedOpportunity): string {
  return item.title || item.reference || `Oportunidad ${item.id}`;
}

function Link({ item, detailHref, onOpen }: { item: SavedOpportunity } & Navigation) {
  function open(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey) {
      event.preventDefault();
      onOpen(item.id);
    }
  }
  return item.available ? <a href={detailHref(item.id)} onClick={open}>{opportunityName(item)}</a>
    : <span>{opportunityName(item)} · no disponible</span>;
}

function CitationText({ cite }: { cite: Citation }) {
  return <div>
    <q>{cite.quote}</q>
    <small>{cite.title} · v{cite.version} · {formatLocator(cite.locator)}</small>
  </div>;
}

function Gaps({ data }: { data: Column["gaps"] }) {
  if (!data || data.status === "sin_generar") return <>Matriz pendiente de generar.</>;
  if (data.status === "invalidado") return <>Matriz desactualizada. Recalcula en la ficha.</>;
  return <>
    <p>Matriz r{data.revision} · {data.status === "aprobado" ? "Aprobada" : "En revisión"}</p>
    {data.incomplete ? <p>Expediente incompleto.</p> : null}
    {!data.assessed ? <p>Requisitos pendientes de confirmar.</p> : null}
    {data.assessed > 0 && !data.items.length ? <p>Sin brechas registradas en la matriz.</p> : null}
    {data.items.length ? <details>
      <summary>{data.items.length} {data.items.length === 1 ? "brecha o requisito pendiente" : "brechas o requisitos pendientes"}</summary>
      <ul>{data.items.map((gap, index) => <li key={index}>
        <strong>{kindLabels[gap.kind]} · {outcomes[gap.outcome]}</strong>
        <p>{gap.reason}</p><CitationText cite={gap.citation} />
      </li>)}</ul>
    </details> : null}
  </>;
}

function Personnel({ data }: { data: Column["personnel"] }) {
  if (!data || data.status !== "listo") return <>Plan de personal pendiente.</>;
  return <>
    {data.availability_pending ? <p>Disponibilidad por confirmar.</p> : null}
    {!data.roles.length ? <p>Cargos por confirmar.</p> : <ul>
      {data.roles.map((item) => <li key={item.role}>
        <strong>{item.role}</strong>
        {item.pending ? <span> · pendiente</span> : null}
        {item.confirmed_periods ? <span> · {item.confirmed_periods} periodos confirmados</span> : null}
        {item.gaps.length ? <ul>{item.gaps.map((gap) => <li key={gap.start}>
          Brecha del {gap.shortfall_percent.replace(".", ",")} % · {gap.start} a {gap.end}
        </li>)}</ul> : null}
      </li>)}
    </ul>}
  </>;
}

function Margins({ data }: { data: Column["margins"] }) {
  if (!data.length) return <>Escenarios pendientes de registrar.</>;
  return <ul>{data.map((item, index) => <li key={index}>
    <strong>{item.name} · {item.currency} · v{item.version}</strong>
    {item.status === "desactualizado" ? <p>Desactualizado. Revisa los supuestos en la ficha.</p>
      : item.status === "ingreso_cero" ? <p>Margen indefinido con ingreso cero.</p>
        : item.margin_percent !== null ? <p>Margen {item.margin_percent.replace(".", ",")} %</p>
          : <p>Margen pendiente.</p>}
    {item.review_status === "pendiente" ? <p>Revisión pendiente.</p> : null}
    {item.missing_amounts.length ? <p>Importes pendientes: {item.missing_amounts.map((key) => labels[key as keyof typeof labels] ?? key).join(", ")}.</p> : null}
    {item.missing_sources.length ? <p>Fuentes pendientes: {item.missing_sources.map((key) => labels[key as keyof typeof labels] ?? key).join(", ")}.</p> : null}
  </li>)}</ul>;
}

function SideBySide({ table, ...navigation }: { table: ComparisonTable } & Navigation) {
  const rows = [
    { name: "Cierre (UTC)", render: (item: Column) => item.reception_at ? formatDateTime(item.reception_at) : "Cierre pendiente de confirmar." },
    { name: "Plazo documentado", render: (item: Column) => item.deadlines.length
      ? <ul>{item.deadlines.map((cite, index) => <li key={index}><CitationText cite={cite} /></li>)}</ul>
      : "Plazo pendiente de confirmar." },
    { name: "Presupuesto publicado", render: (item: Column) => item.published_budget
      ? <>{item.published_budget.amount.replace(".", ",")} · referencia SECOP II. Verifica la moneda en el pliego.</>
      : "Presupuesto pendiente de confirmar." },
    { name: "Brechas", render: (item: Column) => <Gaps data={item.gaps} /> },
    { name: "Personal", render: (item: Column) => <Personnel data={item.personnel} /> },
    { name: "Margen estimado", render: (item: Column) => <Margins data={item.margins} /> },
  ];
  return <div className="shortlist-scroll" role="region" aria-label="Comparación lado a lado" tabIndex={0}>
    <table className="shortlist-table">
      <caption className="sr-only">Comparación de oportunidades guardadas</caption>
      <thead><tr>
        <th scope="col">Criterio</th>
        {table.columns.map((col) => <th key={col.opportunity.id} scope="col">
          <Link item={col.opportunity} {...navigation} />
          {col.opportunity.reference ? <small>{col.opportunity.reference}</small> : null}
        </th>)}
      </tr></thead>
      <tbody>{rows.map((row) => <tr key={row.name}>
        <th scope="row">{row.name}</th>
        {table.columns.map((item) => <td key={item.opportunity.id}>
          {item.opportunity.available ? row.render(item) : "Ficha no disponible."}
        </td>)}
      </tr>)}</tbody>
    </table>
  </div>;
}

export function ShortlistPanel({ selection, viewKey, ...navigation }: {
  selection: Selection; viewKey: string;
} & Navigation) {
  const [show, setShow] = useState(false);
  const [table, setTable] = useState<{ key: string; value: ComparisonTable }>();
  const [failed, setFailed] = useState(false);
  const [load, setLoad] = useState(0);
  const total = selection.data?.items.length ?? 0;
  const revision = selection.data?.revision;
  const refreshSelection = selection.refresh;
  const key = `${revision}/${load}/${viewKey}`;
  useEffect(() => {
    if (!show || total < 2) return;
    const controller = new AbortController();
    fetchShortlistComparison(controller.signal).then(
      (result) => {
        if (controller.signal.aborted) return;
        if (result.revision !== revision) {
          setFailed(true);
          refreshSelection();
        } else {
          setFailed(false);
          setTable({ key, value: result });
        }
      },
      () => { if (!controller.signal.aborted) setFailed(true); },
    );
    return () => controller.abort();
  }, [show, total, revision, key, refreshSelection]);
  function refresh() {
    setFailed(false);
    setLoad((value) => value + 1);
  }
  return <section className="panel shortlist" aria-labelledby="shortlist-title">
    <h2 id="shortlist-title">Lista corta</h2>
    {selection.message ? <p role="status">{selection.message}</p> : null}
    {selection.data ? <>
      <p>{total < 2 ? "Guarda dos o tres oportunidades para compararlas." : `${total} oportunidades guardadas.`}</p>
      {total === 3 ? <p>Quita una oportunidad para guardar otra.</p> : null}
      {total ? <ul className="shortlist-items">{selection.data.items.map((item) => <li key={item.id}>
        <Link item={item} {...navigation} />{" "}
        <button type="button" className="btn btn-s" disabled={selection.busy}
          aria-label={`Quitar ${opportunityName(item)} de la lista corta`}
          onClick={() => void selection.toggle(item.id)}>Quitar</button>
      </li>)}</ul> : null}
      {total >= 2 ? <button type="button" className="btn btn-s" onClick={() => { setShow(!show); if (!show) refresh(); }}>
        {show ? "Ocultar comparación" : "Comparar lista corta"}
      </button> : null}
      {show && total >= 2 ? <>
        {failed ? <p role="status">No se pudo cargar la comparación.</p> : null}
        {table && table.key === key && !failed
          ? <SideBySide table={table.value} {...navigation} />
          : !failed ? <p role="status">Consultando las fichas…</p> : null}
        <button type="button" className="btn btn-s" onClick={refresh}>Actualizar comparación</button>
      </> : null}
    </> : <button type="button" className="btn btn-s" onClick={selection.refresh}>Cargar lista corta</button>}
  </section>;
}

export function ShortlistToggle({ selection, id }: { selection: Selection; id: number }) {
  if (!selection.data) return null;
  const present = selection.data.items.some((item) => item.id === id);
  const full = selection.data.items.length >= 3;
  return <button type="button" className="btn btn-s"
    disabled={selection.busy || (full && !present)}
    onClick={() => void selection.toggle(id)}>
    {present ? "Quitar de la lista corta" : "Guardar en lista corta"}
  </button>;
}
