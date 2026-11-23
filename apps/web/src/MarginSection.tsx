import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "./api/client";
import { costs, fetchHistory, fetchMargin, labels, reviewScenario, saveScenario } from "./api/margin";
import type { Assumption, CostName, Currency, Inputs, MarginWorkspace, Scenario } from "./api/margin";
import { formatColombiaDateTime } from "./design/format";

const costNames = Object.keys(costs) as CostName[];
const status = {
  pendiente: "Revisión pendiente", revisado: "Revisado", desactualizado: "Entradas desactualizadas",
};

function money(amount: string | null, currency: Currency) {
  if (amount === null) return "Pendiente";
  // Decimal del servidor. Conserva precisión y ceros al presentar sin convertir a número JS.
  const [whole, decimals = ""] = amount.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${grouped},${decimals.padEnd(2, "0")} ${currency}`;
}

function AssumptionFields({ name, value, hideAmount }: {
  name: keyof typeof labels; value?: Assumption; hideAmount?: boolean;
}) {
  return <fieldset>
    <legend>{labels[name]}</legend>
    {!hideAmount ? <label>Importe<input name={name} type="text" inputMode="decimal" maxLength={17}
      pattern="[0-9]+([.,][0-9]{1,2})?" defaultValue={value?.amount ?? ""} /></label> : null}
    <label>{hideAmount ? "Justificación y moneda del presupuesto" : "Fuente o supuesto"}
      <input name={`${name}_source`} maxLength={400} required={hideAmount}
        minLength={hideAmount ? 5 : undefined} defaultValue={value?.source ?? ""} />
    </label>
  </fieldset>;
}

function ScenarioForm({ item, budget, busy, save, cancel }: {
  item?: Scenario; budget: string | null; busy: boolean;
  save: (inputs: Inputs, reason: string | null, publishedAmount: string | null) => void;
  cancel: () => void;
}) {
  const [published, setPublished] = useState(item?.inputs.income_mode === "presupuesto_publicado");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const field = (key: string) => String(data.get(key) ?? "").trim();
    const assumption = (key: string): Assumption => ({
      amount: field(key).replace(",", ".") || null, source: field(`${key}_source`) || null,
    });
    const income = assumption("income");
    save({
      name: field("name"), currency: field("currency") as Currency,
      income_mode: published ? "presupuesto_publicado" : "estimado",
      income: published ? { ...income, amount: null } : income,
      costs: {
        direct: assumption("direct"), indirect: assumption("indirect"),
        internal_staff: assumption("internal_staff"), hiring: assumption("hiring"),
        contingency: assumption("contingency"),
      },
    }, field("reason") || null, published ? budget : null);
  }
  return <form className="dossier-form" onSubmit={submit}>
    <fieldset disabled={busy}>
      <legend>{item ? "Editar escenario" : "Nuevo escenario"}</legend>
      <label>Nombre<input name="name" required maxLength={80} defaultValue={item?.inputs.name} /></label>
      <label>Moneda<select name="currency" defaultValue={item?.inputs.currency ?? "COP"}>
        <option>COP</option><option>USD</option><option>EUR</option>
      </select></label>
      <label>Base del ingreso<select value={published ? "publicado" : "estimado"}
        onChange={(event) => setPublished(event.target.value === "publicado")}>
        <option value="estimado">Ingresar mi estimación</option>
        <option value="publicado" disabled={budget === null}>Usar el presupuesto como supuesto de ingreso</option>
      </select></label>
      {published && budget !== null ? <p>Importe de referencia: {budget}. Confirma que corresponde a la moneda seleccionada.</p> : null}
      {published && budget === null ? <p>La referencia publicada no está disponible. Cambia la base del ingreso.</p> : null}
      <AssumptionFields key={String(published)} name="income" hideAmount={published}
        value={item?.inputs.income_mode === "presupuesto_publicado" && !published ? undefined : item?.inputs.income} />
      <p>Escribe 0 cuando el rubro no aplique. Deja vacío un importe por confirmar.</p>
      {costNames.map((name) => <AssumptionFields key={name} name={name} value={item?.inputs.costs[name]} />)}
      <label>Motivo del cambio<input name="reason" minLength={5} maxLength={400} /></label>
      <button type="submit" className="btn btn-s" disabled={published && budget === null}>Guardar escenario</button>{" "}
      <button type="button" className="btn btn-s" onClick={cancel}>Cancelar</button>
    </fieldset>
  </form>;
}

function Totals({ item }: { item: Scenario }) {
  const result = item.calculation;
  const currency = item.inputs.currency;
  return <>
    <dl>
      <div><dt>Ingreso</dt><dd>{money(item.inputs.income.amount, currency)}</dd></div>
      <div><dt>Costos totales</dt><dd>{money(result.total_cost, currency)}</dd></div>
      <div><dt>Utilidad estimada</dt><dd>{money(result.profit, currency)}</dd></div>
      <div><dt>Margen estimado</dt><dd>{result.status === "ingreso_cero" ? "Indefinido con ingreso cero"
        : result.margin_percent !== null ? `${result.margin_percent.replace(".", ",")} %` : "Pendiente"}</dd></div>
    </dl>
    {result.missing_amounts.length ? <p>Importes pendientes: {result.missing_amounts.map((key) => labels[key]).join(", ")}.</p> : null}
    {result.missing_sources.length ? <p>Fuentes pendientes: {result.missing_sources.map((key) => labels[key]).join(", ")}.</p> : null}
  </>;
}

function ScenarioCard({ item, op, canReview, busy, edit, review }: {
  item: Scenario; op: number; canReview: boolean; busy: boolean; edit: () => void;
  review: (reason: string) => void;
}) {
  const [past, setPast] = useState<Scenario[]>();
  const [historyError, setHistoryError] = useState(false);
  return <li className="dossier-analysis">
    <h5>{item.inputs.name}</h5>
    <p>Versión {item.version} · {status[item.review_status]}</p>
    <Totals item={item} />
    <details>
      <summary>Supuestos y versiones de origen</summary>
      <p>Perfil v{item.basis.profile_version} · Comparación {item.basis.comparison_revision ?? "pendiente"}
        {" · "}Corrección de personal {item.basis.staffing_revision ?? "pendiente"}</p>
      {item.inputs.income_mode === "presupuesto_publicado" ? <p>Usa el presupuesto publicado como supuesto revisable.</p> : null}
      <ul>{Object.entries({ income: item.inputs.income, ...item.inputs.costs }).map(([key, input]) => (
        <li key={key}>{labels[key as keyof typeof labels]} · {money(input.amount, item.inputs.currency)}
          {" · "}{input.source ?? "Fuente pendiente"}</li>
      ))}</ul>
      {item.basis.document_versions.length ? <ul aria-label="Versiones del expediente">
        {item.basis.document_versions.map((doc) => <li key={doc.id}>
          <a href={`#documento-${doc.id}`}>Documento {doc.id} · versión {doc.version}</a>
        </li>)}
      </ul> : null}
    </details>
    <button type="button" className="btn btn-s" disabled={busy} onClick={edit}>Editar escenario</button>{" "}
    <button type="button" className="btn btn-s" disabled={busy} onClick={() => {
      setHistoryError(false);
      void fetchHistory(op, item.id).then(setPast).catch(() => setHistoryError(true));
    }}>Ver historial</button>
    {historyError ? <p role="alert">No se pudo abrir el historial.</p> : null}
    {past ? <ol aria-label="Historial financiero">{past.map((version) => <li key={version.version}>
      <p>Versión {version.version} · {version.event} · {formatColombiaDateTime(version.updated_at)} · {version.actor_id}</p>
      {version.reason ? <p>{version.reason}</p> : null}
      <details><summary>Importes, fuentes y versiones guardadas</summary>
        <Totals item={version} />
        <p>Perfil v{version.basis.profile_version} · Comparación {version.basis.comparison_revision ?? "pendiente"}
          {" · "}Personal {version.basis.staffing_revision ?? "pendiente"}</p>
        <ul>{Object.entries({ income: version.inputs.income, ...version.inputs.costs }).map(([key, input]) => (
          <li key={key}>{labels[key as keyof typeof labels]} · {money(input.amount, version.inputs.currency)}
            {" · "}{input.source ?? "Fuente pendiente"}</li>
        ))}</ul>
      </details>
    </li>)}</ol> : null}
    {canReview && item.review_status === "pendiente" && !item.calculation.missing_amounts.length
      && !item.calculation.missing_sources.length ? (
      <form onSubmit={(event) => {
        event.preventDefault();
        review(String(new FormData(event.currentTarget).get("review")));
      }}>
        <label>Nota de revisión<input name="review" required minLength={5} maxLength={400} /></label>{" "}
        <button type="submit" className="btn btn-s" disabled={busy}>Registrar revisión</button>
      </form>
    ) : null}
  </li>;
}

function MarginWorkspaceView({ op }: { op: number }) {
  const [workspace, setWorkspace] = useState<MarginWorkspace>();
  const [editing, setEditing] = useState<Scenario | "new">();
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetchMargin(op, controller.signal).then(
      (value) => { if (!controller.signal.aborted) setWorkspace(value); },
      () => { if (!controller.signal.aborted) setError("No se pudieron cargar los escenarios."); },
    );
    return () => controller.abort();
  }, [op, reload]);
  async function run(action: () => Promise<Scenario>) {
    setError(""); setBusy(true);
    try {
      const saved = await action();
      setWorkspace((previous) => previous ? {
        ...previous, basis: saved.basis, scenarios: [saved, ...previous.scenarios.filter((item) => item.id !== saved.id)],
      } : previous);
      setEditing(undefined);
      try { setWorkspace(await fetchMargin(op)); }
      catch { setError("El escenario se guardó. No se pudo actualizar el resto de los escenarios."); }
    } catch (failure) {
      const conflict = failure instanceof ApiError && failure.status === 409;
      setError(conflict ? "El escenario, sus fuentes o su revisión cambiaron. Consulta la versión actual."
        : "No se guardó la operación. Revisa importe, fuente y moneda.");
      if (conflict) {
        setEditing(undefined);
        setReload((value) => value + 1);
      }
    } finally { setBusy(false); }
  }
  if (!workspace) return error
    ? <><p role="alert">{error}</p><button type="button" onClick={() => {
      setError(""); setReload((value) => value + 1);
    }}>Reintentar</button></>
    : <p role="status">Cargando escenarios…</p>;
  const budget = workspace.basis.published_budget;
  const item = editing === "new" ? undefined : editing;
  return <>
    <p>Presupuesto publicado, solo como referencia: {budget?.amount ?? "no disponible"}.
      {budget ? " Verifica la moneda en el pliego." : ""}</p>
    {workspace.basis.hiring_needs.length ? <details>
      <summary>Brechas de personal para presupuestar</summary>
      <ul>{workspace.basis.hiring_needs.map((need) => (
        <li key={`${need.role}/${need.start}`}>{need.role} · {need.shortfall_percent} % · {need.start} a {need.end}</li>
      ))}</ul>
    </details> : null}
    {workspace.basis.availability_pending ? <p>Hay disponibilidad de personal por confirmar.</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {editing ? <ScenarioForm key={item?.id ?? "new"} item={item} budget={budget?.amount ?? null} busy={busy}
      cancel={() => setEditing(undefined)} save={(values, reason, publishedAmount) => void run(() =>
        saveScenario(op, item?.id, { ...values, base_version: item?.version ?? 0, published_amount: publishedAmount, reason })
      )} /> : <button type="button" className="btn btn-s" disabled={busy || workspace.scenarios.length >= workspace.max_scenarios}
        onClick={() => setEditing("new")}>Nuevo escenario</button>}
    {workspace.scenarios.length ? <ul className="dossier-list" aria-label="Escenarios de margen">
      {workspace.scenarios.map((scenario) => <ScenarioCard key={`${scenario.id}/${scenario.version}`}
        item={scenario} op={op} canReview={workspace.can_review} busy={busy}
        edit={() => setEditing(scenario)} review={(reason) => void run(() => reviewScenario(op, scenario, reason))} />)}
    </ul> : null}
  </>;
}

export function MarginSection({ opportunityId }: { opportunityId: number }) {
  const [opened, setOpened] = useState(false);
  return <details className="dossier-analysis" onToggle={(event) => setOpened(event.currentTarget.open)}>
    <summary>Escenarios de utilidad y margen</summary>
    {opened ? <MarginWorkspaceView op={opportunityId} /> : null}
  </details>;
}
