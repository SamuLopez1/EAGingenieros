import { companyName } from "./brand";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "./api/client";
import { outcomes } from "./api/comparison";
import type { Row } from "./api/comparison";
import { formatLocator } from "./api/extraction";
import { downloadEvidence } from "./api/profile";
import type { Citation } from "./api/requirements";
import { correctStaffing, fetchStaffing } from "./api/staffing";
import type { DemandFields, StaffingPlan } from "./api/staffing";
import { formatColombiaDateTime } from "./design/format";

const coverage = {
  confirmada: "Capacidad confirmada",
  insuficiente: "Capacidad insuficiente",
  por_confirmar: "Disponibilidad por confirmar",
};

function Source({ cite, viewDocument, disabled }: {
  cite: Citation; viewDocument: (id: string, page: number | null) => void; disabled: boolean;
}) {
  return <figure className="analysis-citation">
    <blockquote>{cite.quote}</blockquote>
    <figcaption>{cite.title} · versión {cite.version} · {formatLocator(cite.locator)}{" "}
      <button className="btn btn-s" type="button" disabled={disabled}
        onClick={() => viewDocument(cite.document_id, cite.locator.page)}>Ver documento</button>
    </figcaption>
  </figure>;
}

function demandText(item: DemandFields) {
  return `${item.role ?? "Cargo pendiente"} · ${item.dedication === null ? "dedicación pendiente" : item.dedication + " %"} · ${item.start ?? "inicio pendiente"} a ${item.end ?? "fin pendiente"}`;
}

export function StaffingSection({ opportunityId, rows, viewDocument, disabled }: {
  opportunityId: number; rows: Row[]; viewDocument: (id: string, page: number | null) => void;
  disabled: boolean;
}) {
  const [plan, setPlan] = useState<StaffingPlan>();
  const [rowId, setRowId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchStaffing(opportunityId, controller.signal).then(
      (value) => { if (!controller.signal.aborted) setPlan(value); },
      () => { if (!controller.signal.aborted) setError("No se pudo consultar encaje y personal."); },
    );
    return () => controller.abort();
  }, [opportunityId, retry]);

  function openEvidence(documentId: string) {
    void downloadEvidence(documentId).catch(() => setError("No se pudo abrir la evidencia empresarial."));
  }

  async function correct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!plan || !rowId) return;
    const data = new FormData(event.currentTarget);
    const field = (key: string) => String(data.get(key) ?? "").trim() || null;
    setError("");
    setBusy(true);
    try {
      setPlan(await correctStaffing(opportunityId, plan, {
        row_id: rowId, role: field("role"), dedication: field("dedication"),
        start: field("start"), end: field("end"), reason: field("reason") ?? "",
      }));
      setRowId("");
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 409) {
        setError("La comparación o el historial cambió. Vuelve a revisar los datos.");
        setPlan(undefined);
        setRetry((value) => value + 1);
      } else setError("No se guardó la corrección. Comprueba los campos y el periodo.");
    } finally { setBusy(false); }
  }

  const demands = new Map(plan?.demands.map((demand) => [demand.row_id, demand]));
  const selected = demands.get(rowId);
  return <section className="dossier-analysis" aria-labelledby="staffing-title">
    <h4 id="staffing-title">Encaje y personal</h4>
    {error ? <div><p role="alert">{error}</p>
      {!plan ? <button type="button" className="btn btn-s" onClick={() => {
        setError(""); setRetry((value) => value + 1);
      }}>Actualizar encaje y personal</button> : null}
    </div> : null}
    {!plan && !error ? <p role="status">Consultando disponibilidad…</p> : null}
    {plan?.status === "comparacion_pendiente" ? <p>Actualiza la comparación para revisar el encaje y la disponibilidad.</p> : null}
    {plan?.status === "listo" ? <>
      <p>Perfil v{plan.profile_version} · Comparación r{plan.comparison_revision} · Planificación para revisión humana.</p>
      {plan.incomplete ? <p>El expediente está incompleto. Las exigencias adicionales están por confirmar.</p> : null}
      <h5>Encaje por línea de servicio</h5>
      {plan.service_fit.map((line, index) => <div key={line.line ?? index}>
        <strong>{line.line ?? "Línea por confirmar"} · {line.status === "respaldado" ? "Con respaldo" : "Por confirmar"}</strong>
        <p>{line.reason}</p>
        {line.citations.map((cite, index) => <Source key={index} cite={cite} viewDocument={viewDocument} disabled={disabled} />)}
        {line.support.map((entry, index) => <div key={index}>
          <p>{entry.title} · {entry.category}</p>
          {entry.evidence.map((ref, index) => <button key={index} type="button" className="btn btn-s"
            onClick={() => openEvidence(ref.document_id)}>Evidencia {companyName} · {ref.locator}</button>)}
        </div>)}
      </div>)}
      {plan.qualifying_gaps.length ? <div>
        <h5>Brechas habilitantes</h5>
        {plan.qualifying_gaps.map((gap, index) => <div key={index}>
          <p><strong>{outcomes[gap.outcome]}</strong> · {gap.reason}</p>
          <Source cite={gap.citation} viewDocument={viewDocument} disabled={disabled} />
        </div>)}
      </div> : null}
      <h5>Disponibilidad por cargo y periodo</h5>
      {plan.roles.map((role) => <div key={role.role}>
        <h6>{role.role}</h6>
        {!role.periods.length ? <p>Confirma dedicación y fechas para estimar la cobertura.</p> : null}
        <ul>{role.periods.map((period) => <li key={period.start}>
          <strong>{period.start} a {period.end} · {coverage[period.status]}</strong>
          <p>Exigida {period.required} % · Registrada {period.recorded === null ? "por confirmar" : period.recorded + " %"}</p>
          <p>{period.reason}</p>
          {period.evaluate_staffing ? <p>Evaluar contratación o reasignación de {role.role} al {period.shortfall} %
            entre {period.start} y {period.end}, según la cobertura registrada.</p> : null}
          {period.verify_availability ? <p>Confirmar disponibilidad con Talento Humano para este periodo.</p> : null}
          {period.demand_ids.length ? <details>
            <summary>Exigencias citadas del periodo</summary>
            {period.demand_ids.map((id) => {
              const demand = demands.get(id);
              return demand ? <Source key={id} cite={demand.citation} viewDocument={viewDocument} disabled={disabled} /> : null;
            })}
          </details> : null}
          {period.evidence.map((ref, index) => <button key={index} type="button" className="btn btn-s"
            onClick={() => openEvidence(ref.document_id)}>Evidencia de disponibilidad · {ref.locator}</button>)}
        </li>)}</ul>
      </div>)}
      {!plan.demands.length ? <p>No se identificaron exigencias de personal citables. Verifica el pliego y las adendas.</p> : null}
      {plan.demands.length ? <details>
        <summary>Exigencias y datos por confirmar</summary>
        {plan.demands.map((demand) => <div key={demand.row_id}>
          <p>{demandText(demand)}{demand.corrected ? " · Corregido" : ""}</p>
          {demand.missing.length ? <p>Pendiente: {demand.missing.join(", ")}.</p> : null}
          <Source cite={demand.citation} viewDocument={viewDocument} disabled={disabled} />
        </div>)}
      </details> : null}
      {plan.can_correct && rows.length ? <form className="dossier-form" onSubmit={(event) => void correct(event)}>
        <label>Requisito de personal<select value={rowId} onChange={(event) => setRowId(event.target.value)} disabled={busy}>
          <option value="">Seleccionar para corregir</option>
          {rows.map((row) => <option value={row.id} key={row.id}>{row.citation.quote}</option>)}
        </select></label>
        {rowId ? <fieldset key={rowId} disabled={busy}>
          <legend>Corrección de personal</legend>
          <label>Cargo<input name="role" maxLength={160} defaultValue={selected?.role ?? ""} /></label>
          <label>Dedicación exigida (%)<input name="dedication" type="number" min=".01" max="10000" step=".01"
            defaultValue={selected?.dedication ?? ""} /></label>
          <label>Inicio<input name="start" type="date" defaultValue={selected?.start ?? ""} /></label>
          <label>Fin<input name="end" type="date" defaultValue={selected?.end ?? ""} /></label>
          <label>Motivo de la corrección<textarea name="reason" minLength={5} maxLength={500} required /></label>
          <button type="submit" className="btn btn-s">Guardar corrección de personal</button>
        </fieldset> : null}
      </form> : null}
      {plan.audit.length ? <details>
        <summary>Historial de correcciones de personal</summary>
        <ol>{plan.audit.map((event) => <li key={event.sequence}>
          {formatColombiaDateTime(event.created_at)} · {event.actor_id} · Comparación r{event.comparison_revision}
          <p>{event.reason}</p>
          <p>{demandText(event.previous)} → {demandText(event.corrected)}</p>
        </li>)}</ol>
      </details> : null}
    </> : null}
  </section>;
}
