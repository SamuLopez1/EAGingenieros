import { useEffect, useState } from "react";
import { fetchExtraction, requestExtraction } from "./api/extraction";
import type { Extraction, Locator } from "./api/extraction";

const states: Record<Extraction["status"], string> = {
  sin_extraccion: "Sin extracción",
  pendiente: "En cola",
  procesando: "Extrayendo texto",
  listo: "Extracción disponible",
  revision: "Cobertura insuficiente · requiere revisión",
  fallido: "La extracción falló",
};
const messages: Record<string, string> = {
  archivo_cifrado: "El archivo está cifrado.",
  archivo_ilegible: "No fue posible leer el formato o su contenido.",
  documento_no_disponible: "La versión del documento dejó de estar disponible.",
  elementos_no_textuales: "Hay elementos gráficos o anidados que requieren revisión manual.",
  formato_no_soportado: "El formato no está habilitado para extracción.",
  integridad_documento: "Los bytes no coinciden con la versión registrada.",
  limite_archivo: "El archivo supera el tamaño configurado.",
  limite_celdas: "La hoja excede el rango de celdas procesable.",
  limite_hojas: "Se alcanzó el máximo de hojas.",
  limite_memoria: "Se alcanzó el presupuesto de memoria.",
  limite_ocr: "Se alcanzó el máximo de páginas con OCR.",
  limite_paginas: "El documento supera el máximo de páginas.",
  limite_tabla: "La tabla excede el rango de filas o celdas procesable.",
  limite_texto: "Se alcanzó el máximo de texto o fragmentos.",
  ocr_baja_confianza: "El texto reconocido tiene confianza baja o sin medir.",
  ocr_fallido: "El OCR no pudo completar esta página.",
  ocr_no_disponible: "El motor OCR no está disponible.",
  ocr_sin_texto_suficiente: "El OCR no obtuvo texto suficiente.",
  pagina_ilegible: "No fue posible leer la capa de texto de la página.",
  sin_texto: "La extracción no obtuvo texto. Comprueba el documento original.",
  tiempo_agotado: "Se agotó el tiempo de procesamiento.",
  worker_fallido: "El proceso de extracción no pudo entregar un resultado.",
  worker_interrumpido: "La tarea se interrumpió antes de obtener un resultado.",
};

function label(loc: Locator): string {
  if (loc.page !== null) return `Página ${loc.page}`;
  if (loc.sheet !== null) return [`Hoja ${loc.sheet}`, loc.cell].filter(Boolean).join(" · ");
  return [
    loc.section ? `Sección ${loc.section}` : null,
    loc.paragraph !== null ? `Párrafo ${loc.paragraph}` : null,
    loc.table !== null ? `Tabla ${loc.table}` : null,
    loc.row !== null ? `fila ${loc.row}` : null,
    loc.column !== null ? `celda ${loc.column}` : null,
  ].filter(Boolean).join(" · ");
}

export function DocumentExtraction({
  opportunityId, documentId, version,
}: { opportunityId: number; documentId: string; version: number }) {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState<Extraction | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(25);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const result = await fetchExtraction(opportunityId, documentId, controller.signal);
        if (controller.signal.aborted) return;
        setCurrent(result);
        setError("");
        if (result.status === "pendiente" || result.status === "procesando") {
          timer = setTimeout(() => void refresh(), 2000);
        }
      } catch {
        if (!controller.signal.aborted) setError("No fue posible consultar la extracción.");
      }
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [open, opportunityId, documentId, revision]);

  async function start(retry: boolean) {
    setBusy(true);
    setError("");
    try {
      setCurrent(await requestExtraction(opportunityId, documentId, retry));
      setRevision((value) => value + 1);
      setVisible(25);
    } catch {
      setError("No fue posible encolar la extracción de esta versión.");
    } finally {
      setBusy(false);
    }
  }

  const result = current?.result;
  const retry = current?.status === "revision" || current?.status === "fallido";
  return (
    <details className="document-extraction" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>Extracción de texto · versión {version}</summary>
      {open ? <>
        <p role="status">{current ? states[current.status] : error ? "" : "Consultando extracción…"}</p>
        {current?.status === "sin_extraccion" || retry ? (
          <button type="button" className="btn btn-s" disabled={busy} onClick={() => void start(retry)}>
            {retry ? "Reintentar extracción" : "Extraer texto"}
          </button>
        ) : null}
        {error ? (
          <>
            <p role="alert">{error}</p>
            <button type="button" className="btn btn-s"
                    onClick={() => setRevision((value) => value + 1)}>Actualizar estado</button>
          </>
        ) : null}
        {result?.error_code ? <p>{messages[result.error_code] ?? "Error de extracción."}</p> : null}
        {result?.warnings.length ? (
          <details>
            <summary>Avisos de cobertura ({result.warnings.length})</summary>
            <ul className="extraction-notices">
              {result.warnings.map((warning, index) => (
                <li key={index}>
                  {warning.locator ? `${label(warning.locator)} · ` : ""}
                  {messages[warning.code] ?? "Revisar manualmente la cobertura."}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
        {result?.fragments.length ? (
          <>
            <p>{result.fragments.length} fragmentos · oportunidad {opportunityId} · versión {version}</p>
            <ol className="extraction-fragments">
              {result.fragments.slice(0, visible).map((fragment, index) => (
                <li key={index}>
                  <strong>{label(fragment.locator)}</strong>
                  {fragment.method === "ocr" ? (
                    <span> · OCR{fragment.confidence !== null ? ` ${Math.round(fragment.confidence)}%` : ""}</span>
                  ) : null}
                  <p>{fragment.text}</p>
                </li>
              ))}
            </ol>
            {visible < result.fragments.length ? (
              <button type="button" className="btn btn-s" onClick={() => setVisible((value) => value + 25)}>
                Mostrar más fragmentos
              </button>
            ) : null}
          </>
        ) : null}
      </> : null}
    </details>
  );
}
