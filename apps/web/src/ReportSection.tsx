import { companyName, simulatedMailbox } from "./brand";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "./api/client";
import { fetchOutbox, fetchReport, sendReport } from "./api/report";
import type { Delivery } from "./api/report";
import { formatColombiaDateTime } from "./design/format";

const labels: Record<Delivery["state"], string> = {
  en_curso: "En curso",
  aceptado: "Aceptado por el proveedor",
  reintentar: "Se puede reintentar con la misma clave",
  rechazado: "Rechazado por el proveedor",
  incierto: "Entrega por confirmar. Verifica antes de otro envío.",
  bloqueado: "Bloqueado por cambio de aprobación",
};

function failure(error: unknown) {
  if (error instanceof ApiError && error.status === 409) return "La aprobación o el envío cambió. Actualiza la ficha.";
  if (error instanceof ApiError && error.status === 403) return "La cuenta o el destinatario no tiene autorización.";
  if (error instanceof ApiError && error.status === 503) return "El correo de informes no está configurado.";
  return "No fue posible completar la operación.";
}

export function ReportSection({ opportunityId, revision, canSend }: {
  opportunityId: number; revision: number; canSend: boolean;
}) {
  const [preview, setPreview] = useState<string>();
  const [mail, setMail] = useState<Awaited<ReturnType<typeof fetchOutbox>>>();
  const [recipient, setRecipient] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  useEffect(() => {
    if (!canSend) return;
    const controller = new AbortController();
    fetchOutbox(opportunityId, revision, controller.signal).then(
      (value) => { if (!controller.signal.aborted) setMail(value); },
      () => { if (!controller.signal.aborted) setError("No se pudo consultar la auditoría de correo."); },
    );
    return () => controller.abort();
  }, [canSend, opportunityId, revision]);

  async function open(download: boolean) {
    setBusy(true);
    setError("");
    try {
      const url = URL.createObjectURL(await fetchReport(opportunityId, revision, download));
      if (!download) setPreview(url);
      else {
        const link = document.createElement("a");
        link.href = url;
        link.download = `${companyName.toLowerCase()}-${opportunityId}-r${revision}.pdf`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch (error) {
      setPreview(undefined);
      setError(failure(error));
    } finally { setBusy(false); }
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!recipient || busy || !mail) return;
    setError("");
    setBusy(true);
    try {
      const result = await sendReport(opportunityId, revision, recipient);
      setMail({ ...mail, deliveries: [result, ...mail.deliveries.filter((item) => item.id !== result.id)] });
    } catch (error) { setError(failure(error)); }
    finally { setBusy(false); }
  }

  const last = mail?.deliveries.find((item) => item.recipient === recipient);
  const canDispatch = !last || last.state === "reintentar" || last.state === "en_curso";
  return <section id="informe-aprobado" className="dossier-analysis" aria-labelledby="report-title">
    <h4 id="report-title">Informe aprobado · revisión {revision}</h4>
    {canSend && simulatedMailbox ? <p><a href="/api/demo-mailbox" target="_blank"
      rel="noreferrer">Abrir buzón simulado</a></p> : null}
    <button className="btn btn-s" type="button" disabled={busy} onClick={() => void open(false)}>Vista previa del PDF</button>{" "}
    <button className="btn btn-s" type="button" disabled={busy} onClick={() => void open(true)}>Descargar PDF privado</button>
    {preview ? <div>
      <button type="button" className="btn btn-s" onClick={() => setPreview(undefined)}>Cerrar vista previa</button>
      <iframe title={`Informe aprobado, revisión ${revision}`} src={preview} className="report-preview" />
    </div> : null}
    {error ? <p role="alert">{error}</p> : null}
    {canSend && mail ? <>
      {mail.configured ? <form className="dossier-form" onSubmit={(event) => void send(event)}>
        <label>Destinatario autorizado<select required value={recipient} disabled={busy}
          onChange={(event) => setRecipient(event.target.value)}>
          <option value="">Seleccionar destinatario</option>
          {mail.recipients.map((address) => <option key={address}>{address}</option>)}
        </select></label>
        <button type="submit" className="btn btn-s" disabled={busy || !recipient || !canDispatch}>
          {last ? "Comprobar o reintentar envío" : "Enviar enlace privado"}
        </button>
      </form> : <p>El correo de informes está pendiente de configuración.</p>}
      {mail.deliveries.length ? <details>
        <summary>Auditoría de correo</summary>
        <ul>{mail.deliveries.map((item) => <li key={item.id}>
          <p>{item.recipient} · {labels[item.state]} · {formatColombiaDateTime(item.updated_at)}</p>
          <p>{item.attempts.length} {item.attempts.length === 1 ? "intento" : "intentos"}</p>
          <ol>{item.attempts.map((attempt, index) => <li key={index}>
            {labels[attempt.state]} · {formatColombiaDateTime(attempt.started_at)} · {attempt.actor_id}
          </li>)}</ol>
        </li>)}</ul>
      </details> : null}
    </> : null}
  </section>;
}
