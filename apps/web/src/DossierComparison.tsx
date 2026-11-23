import { StaffingSection } from "./StaffingSection";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "./api/client";
import { approveComparison, compare, correctComparison, outcomes, readComparison } from "./api/comparison";
import type { Comparison, Outcome } from "./api/comparison";
import { formatLocator } from "./api/extraction";
import { downloadEvidence } from "./api/profile";
import { formatColombiaDateTime } from "./design/format";

const statusLabels = {
  sin_generar: "Sin comparación",
  borrador: "Borrador para revisión",
  aprobado: "Comparación aprobada",
  invalidado: "Comparación desactualizada. La aprobación anterior no está vigente.",
};
const inputLabels: Record<string, string> = {
  expediente: "Expediente", perfil: "Perfil", retencion: "Retención", reglas: "Reglas",
};
const typeLabels = { habilitante: "Habilitante", evaluable: "Evaluable", obligacion: "Obligación de ejecución" };

export function DossierComparison({ opportunityId, role, disabled, openDocument }: {
  opportunityId: number; role: "administrador" | "analista"; disabled: boolean;
  openDocument: (id: string) => void;
}) {
  const [result, setResult] = useState<Comparison>();
  const [editing, setEditing] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const initialRequest = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    initialRequest.current = controller;
    readComparison(opportunityId, controller.signal).then(
      (value) => { if (!controller.signal.aborted) setResult(value); },
      () => { /* El botón permite recuperar el estado y generar el borrador. */ },
    );
    return () => controller.abort();
  }, [opportunityId]);

  async function run(action: () => Promise<Comparison>) {
    initialRequest.current?.abort();
    setBusy(true);
    setError("");
    try {
      setResult(await action());
      setEditing(undefined);
    } catch (failure) {
      const status = failure instanceof ApiError ? failure.status : 0;
      setError(status === 409 ? "La comparación cambió o le faltan requisitos o perfil. Actualízala."
        : status === 422 ? "Revisa la justificación y selecciona evidencia verificada para acreditar cumplimiento."
          : "No fue posible completar la operación.");
      if (status === 409) {
        try { setResult(await readComparison(opportunityId)); }
        catch { setResult(undefined); }
      }
    } finally { setBusy(false); }
  }

  function submitCorrection(event: FormEvent<HTMLFormElement>, rowId: string, snapshot: Comparison) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const index = String(data.get("profile") ?? "");
    void run(() => correctComparison(opportunityId, snapshot, {
      row_id: rowId, outcome: String(data.get("outcome")) as Outcome, reason: String(data.get("reason")),
      profile_entry: index === "" ? null : Number(index),
    }));
  }

  function submitApproval(event: FormEvent<HTMLFormElement>, snapshot: Comparison) {
    event.preventDefault();
    const reason = String(new FormData(event.currentTarget).get("approval"));
    void run(() => approveComparison(opportunityId, snapshot, reason));
  }

  const blocked = disabled || busy;
  return <section className="dossier-analysis" aria-labelledby="comparison-title">
    <h4 id="comparison-title">Comparación con EAG</h4>
    <button type="button" className="btn btn-s" disabled={blocked}
      onClick={() => void run(() => compare(opportunityId))}>Comparar con EAG</button>
    {error ? <p role="alert">{error}</p> : null}
    {result && result.revision > 0 ? <>
      <p role="status">{statusLabels[result.status]} · Revisión {result.revision} · Perfil {result.profile_version || "sin registrar"}</p>
      {result.invalidated_by.length ? <p>Cambios: {result.invalidated_by.map((key) => inputLabels[key] ?? key).join(", ")}.</p> : null}
      {result.incomplete ? <p>El expediente está incompleto. Verifica los avisos en «Resumen y requisitos».</p> : null}
      {result.status !== "invalidado" && !result.rows.length ? <p>No hay requisitos con cita para comparar.</p> : null}
      <ul className="dossier-list" aria-label="Matriz de requisitos">
        {result.rows.map((row) => <li key={row.id}>
          <div>
            <strong>{typeLabels[row.kind as keyof typeof typeLabels]} · {outcomes[row.outcome]}</strong>
            {row.kind === "habilitante" && row.outcome !== "cumple" ? <p>Brecha habilitante por resolver.</p> : null}
            <p>{row.reason}{row.corrected ? " · Corregido" : ""}</p>
            <figure className="analysis-citation">
              <blockquote>{row.citation.quote}</blockquote>
              <figcaption>
                {row.citation.title} · versión {row.citation.version} · {formatLocator(row.citation.locator)}{" "}
                <button type="button" className="btn btn-s" disabled={blocked}
                  onClick={() => openDocument(row.citation.document_id)}>Abrir evidencia del expediente</button>
              </figcaption>
            </figure>
            {row.profile_sources.length ? <ul aria-label="Evidencias del perfil">
              {row.profile_sources.map((source) => <li key={source.index}>
                <p>{source.title} · perfil v{result.profile_version}</p>
                {source.evidence.map((evidence) => <button type="button" className="btn btn-s"
                  key={`${evidence.document_id}/${evidence.locator}`}
                  onClick={() => void downloadEvidence(evidence.document_id).catch(() =>
                    setError("No se pudo descargar la evidencia empresarial."))}>
                  Abrir evidencia EAG · {evidence.locator}
                </button>)}
              </li>)}
            </ul> : <p>Sin evidencia asociada del perfil.</p>}
            {editing === row.id ? <form className="dossier-form" onSubmit={(event) => submitCorrection(event, row.id, result)}>
              <label>Resultado<select name="outcome" defaultValue={row.outcome}>
                {Object.entries(outcomes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </select></label>
              <label>Evidencia verificada<select name="profile" defaultValue="">
                <option value="">Seleccionar evidencia</option>
                {result.profile_options.map((option) => <option key={option.index} value={option.index}>{option.title}</option>)}
              </select></label>
              <label>Justificación<textarea name="reason" minLength={5} maxLength={500} required /></label>
              <button type="submit" className="btn btn-s" disabled={blocked}>Guardar corrección</button>
              <button type="button" className="btn btn-s" onClick={() => setEditing(undefined)}>Cancelar</button>
            </form> : <button type="button" className="btn btn-s" disabled={blocked}
              onClick={() => setEditing(row.id)}>Corregir requisito</button>}
          </div>
        </li>)}
      </ul>
      {role === "administrador" && result.status === "borrador" && result.rows.length && result.profile_version
        ? <form className="dossier-form" onSubmit={(event) => submitApproval(event, result)}>
          <label>Justificación de aprobación<textarea name="approval" minLength={5} maxLength={500} required /></label>
          <button type="submit" className="btn btn-s" disabled={blocked || Boolean(editing)}>Aprobar comparación</button>
        </form> : null}
      {result.status === "borrador" || result.status === "aprobado" ? (
        <StaffingSection key={`${opportunityId}/${result.revision}/${result.fingerprint}`}
          opportunityId={opportunityId} rows={result.rows} />
      ) : null}
      {result.audit.length ? <details>
        <summary>Historial de revisión</summary>
        <ol>
          {result.audit.map((event) => <li key={event.revision}>
            Revisión {event.revision} · {event.action} · {formatColombiaDateTime(event.created_at)}
            {" · "}{event.actor_role} · {event.actor_id} · perfil v{event.profile_version}
            {event.before && event.after ? <p>{outcomes[event.before]} → {outcomes[event.after]}</p> : null}
            {event.reason ? <p>{event.reason}</p> : null}
            <ul>{event.document_versions.map((doc) => <li key={doc.id}>{doc.id} · versión {doc.version}</li>)}</ul>
          </li>)}
        </ol>
      </details> : null}
    </> : null}
  </section>;
}
