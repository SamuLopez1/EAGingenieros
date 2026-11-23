import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { DocumentExtraction } from "./DocumentExtraction";
import { ApiError } from "./api/client";
import {
  downloadDocument,
  fetchDossier,
  importOfficial,
  updateDocument,
  uploadDocument,
} from "./api/documents";
import type { DocumentKind, Dossier, DossierDocument } from "./api/documents";
import { formatColombiaDateTime } from "./design/format";

const statuses: Record<DossierDocument["status"], string> = {
  disponible: "Disponible",
  cuarentena: "En cuarentena",
  rechazado: "Rechazado",
  vencido: "Vencido",
};
const kinds: Record<DocumentKind, string> = { pliego: "Pliego", adenda: "Adenda" };
type Load = { kind: "loading" } | { kind: "error" } | { kind: "ready"; data: Dossier };

function actionError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 413) return "El archivo o el expediente supera el límite de tamaño.";
    if (error.status === 422) return "El archivo fue rechazado por los controles de seguridad.";
    if (error.status === 502) return "SECOP no entregó el archivo. Puedes cargarlo manualmente.";
    if (error.status === 409 || error.status === 410) return "El documento no está disponible.";
  }
  return "No fue posible completar la operación. Vuelve a intentarlo.";
}

export function DossierSection({
  opportunityId,
  role,
}: {
  opportunityId: number;
  role: "administrador" | "analista";
}) {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetchDossier(opportunityId, controller.signal).then(
      (data) => { if (!controller.signal.aborted) setLoad({ kind: "ready", data }); },
      () => { if (!controller.signal.aborted) setLoad({ kind: "error" }); },
    );
    return () => controller.abort();
  }, [opportunityId, revision]);

  function refresh() {
    setRevision((value) => value + 1);
  }

  async function mutate(action: () => Promise<DossierDocument>, success: string) {
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const item = await action();
      setNotice(item.status === "cuarentena" ? "Archivo guardado en cuarentena." : success);
      refresh();
      return true;
    } catch (failure) {
      setError(actionError(failure));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const file = values.get("file");
    const title = String(values.get("title") ?? "").trim();
    const kind = values.get("kind") === "adenda" ? "adenda" : "pliego";
    if (!(file instanceof File) || !file.size || !title) return;
    if (load.kind === "ready" && file.size > load.data.max_file_bytes) {
      setNotice("");
      setError("El archivo supera el límite de tamaño.");
      return;
    }
    if (await mutate(
      () => uploadDocument(opportunityId, kind, title, file), "Documento cargado.",
    )) form.reset();
  }

  async function download(item: DossierDocument) {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const blob = await downloadDocument(opportunityId, item);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = item.filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) {
      setError(actionError(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="dossier" aria-labelledby="dossier-title">
      <h3 id="dossier-title">Expediente</h3>
      {load.kind === "loading" ? <p role="status">Cargando expediente…</p> : null}
      {load.kind === "error" ? (
        <div>
          <p>No fue posible cargar el expediente.</p>
          <button type="button" className="btn btn-s" onClick={refresh}>Reintentar expediente</button>
        </div>
      ) : null}
      {load.kind === "ready" ? (
        <>
          {load.data.missing_pliego ? <p>Falta un pliego disponible. El expediente puede estar incompleto.</p> : null}
          {load.data.official.length ? (
            <ul className="dossier-list" aria-label="Documentos oficiales validados">
              {load.data.official.map((item) => (
                <li key={item.id}>
                  <span>{kinds[item.kind]} · {item.title}</span>
                  <button className="btn btn-s" type="button" disabled={busy} onClick={() =>
                    void mutate(() => importOfficial(opportunityId, item.id), "Documento oficial incorporado.")
                  }>
                    Descargar desde SECOP
                  </button>
                </li>
              ))}
            </ul>
          ) : <p>Sin descarga oficial validada para esta oportunidad.</p>}
          <form className="dossier-form" onSubmit={(event) => void upload(event)}>
            <label>Tipo
              <select name="kind" defaultValue="pliego">
                <option value="pliego">Pliego</option>
                <option value="adenda">Adenda</option>
              </select>
            </label>
            <label>Nombre del documento
              <input name="title" maxLength={140} required placeholder="Pliego principal o Adenda 1" />
            </label>
            <label>Archivo (PDF, DOCX o XLSX)
              <input name="file" type="file" accept=".pdf,.docx,.xlsx" required />
            </label>
            <button className="btn btn-p" disabled={busy} type="submit">Cargar archivo</button>
          </form>
          {load.data.documents.length ? (
            <ul className="dossier-list" aria-label="Documentos del expediente">
              {load.data.documents.map((item) => (
                <li key={item.id}>
                  <div>
                    <strong>{kinds[item.kind]} · {item.title}</strong>
                    <p>{item.filename} · {item.origin === "oficial" ? "SECOP II" : "Carga manual"} · Versión {item.version}</p>
                    <p>{statuses[item.status]}{item.under_review ? " · En revisión" : ""}</p>
                    <p>Retención hasta {formatColombiaDateTime(item.retention_until)}</p>
                    {item.source_record_id ? <p>Referencia oficial: {item.source_record_id}</p> : null}
                  </div>
                  <div className="dossier-actions">
                    {item.status === "disponible" ? (
                      <>
                        <button type="button" className="btn btn-s" disabled={busy} onClick={() => void download(item)}>
                          Descargar archivo
                        </button>
                        {!item.under_review ? (
                          <button type="button" className="btn btn-s" disabled={busy} onClick={() => void mutate(
                            () => updateDocument(opportunityId, item.id, "review"), "Versión en revisión.",
                          )}>
                            Marcar en revisión
                          </button>
                        ) : null}
                      </>
                    ) : null}
                    {item.status === "cuarentena" && role === "administrador" ? (
                      <button type="button" className="btn btn-s" disabled={busy} onClick={() => void mutate(
                        () => updateDocument(opportunityId, item.id, "rescan"), "Análisis actualizado.",
                      )}>Volver a analizar</button>
                    ) : null}
                  </div>
                  {item.status === "disponible" ? (
                    <DocumentExtraction opportunityId={opportunityId} documentId={item.id} version={item.version} />
                  ) : null}
                </li>
              ))}
            </ul>
          ) : <p>El expediente está vacío.</p>}
        </>
      ) : null}
      {notice ? <p role="status">{notice}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
