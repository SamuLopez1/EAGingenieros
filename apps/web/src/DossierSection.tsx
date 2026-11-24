import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { DossierAnalysis } from "./DossierAnalysis";
import { DossierComparison } from "./DossierComparison";
import { DocumentExtraction } from "./DocumentExtraction";
import { MarginSection } from "./MarginSection";
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

type Preview = { url: string; title: string; filename: string; page: number | null };

function saveDocument(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

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
  const [preview, setPreview] = useState<Preview>();
  const [viewError, setViewError] = useState("");
  const previewHeading = useRef<HTMLHeadingElement>(null);
  const previewRequest = useRef<AbortController | null>(null);

  useEffect(() => () => previewRequest.current?.abort(), []);
  useEffect(() => {
    if (!preview) return;
    previewHeading.current?.focus();
    return () => URL.revokeObjectURL(preview.url);
  }, [preview]);

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
      saveDocument(blob, item.filename);
    } catch (failure) {
      setError(actionError(failure));
    } finally {
      setBusy(false);
    }
  }

  async function viewDocument(id: string, page: number | null) {
    if (load.kind !== "ready" || busy) return;
    const item = load.data.documents.find((doc) => doc.id === id);
    setViewError("");
    setPreview(undefined);
    if (!item || item.status !== "disponible") {
      setViewError("El documento citado no está disponible en este expediente.");
      return;
    }
    const controller = new AbortController();
    previewRequest.current = controller;
    setBusy(true);
    try {
      const blob = await downloadDocument(opportunityId, item, controller.signal);
      // El endpoint de descarga devuelve todos los formatos como octet-stream.
      const isPdf = item.filename.toLowerCase().endsWith(".pdf")
        && await blob.slice(0, 5).text() === "%PDF-";
      if (controller.signal.aborted) return;
      if (!isPdf) {
        saveDocument(blob, item.filename);
        return;
      }
      const pdf = blob.slice(0, blob.size, "application/pdf");
      setPreview({ url: URL.createObjectURL(pdf), title: item.title, filename: item.filename, page });
    } catch (failure) {
      if (!controller.signal.aborted) setViewError(actionError(failure));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  const previewUrl = preview && (preview.page ? preview.url + "#page=" + preview.page : preview.url);

  return (
    <section className="dossier" aria-labelledby="dossier-title">
      <h3 id="dossier-title">Expediente</h3>
      {preview && previewUrl ? (
        <section className="dossier-analysis" aria-labelledby="document-preview-title">
          <h4 id="document-preview-title" ref={previewHeading} tabIndex={-1}>
            {preview.title}{preview.page ? " · Página " + preview.page : ""}
          </h4>
          <a className="btn btn-s" href={previewUrl} target="_blank" rel="noreferrer">Abrir PDF en otra pestaña</a>{" "}
          <a className="btn btn-s" href={preview.url} download={preview.filename}>Descargar PDF del documento</a>{" "}
          <button className="btn btn-s" type="button" onClick={() => setPreview(undefined)}>Cerrar vista del documento</button>
          <iframe title="Vista previa privada del documento" src={previewUrl} className="report-preview" />
        </section>
      ) : null}
      {viewError ? <p role="alert">{viewError}</p> : null}
      {load.kind === "loading" ? <p role="status">Cargando expediente…</p> : null}
      {load.kind === "error" ? (
        <div>
          <p>No fue posible cargar el expediente.</p>
          <button type="button" className="btn btn-s" onClick={refresh}>Reintentar expediente</button>
        </div>
      ) : null}
      {load.kind === "ready" ? (
        <>
          <DossierAnalysis key={`${opportunityId}/${revision}`} opportunityId={opportunityId}
            documents={load.data.documents} disabled={busy} viewDocument={(id, page) => void viewDocument(id, page)} />
          <DossierComparison key={`comparacion/${opportunityId}/${revision}`} opportunityId={opportunityId}
            role={role} disabled={busy} viewDocument={(id, page) => void viewDocument(id, page)} openDocument={(id) => {
              const item = load.data.documents.find((doc) => doc.id === id);
              if (item) void download(item);
            }} />
          <MarginSection key={`margen/${opportunityId}/${revision}`} opportunityId={opportunityId} />
          {load.data.missing_pliego ? <p>Falta un pliego disponible. El expediente puede estar incompleto.</p> : null}
          {load.data.official.length ? (
            <ul className="dossier-list" aria-label="Documentos oficiales validados">
              {load.data.official.map((item) => (
                <li key={item.id} id={`documento-${item.id}`}>
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
                <li key={item.id} id={`documento-${item.id}`}>
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
