import { useState } from "react";
import type { DossierDocument } from "./api/documents";
import { formatLocator } from "./api/extraction";
import { analyzeDossier } from "./api/requirements";
import type { Analysis, Citation, Finding } from "./api/requirements";

const descriptions: Record<string, string> = {
  sin_pliego_seleccionado: "Falta un pliego disponible marcado para revisión.",
  referencia_oficial_sin_seleccionar: "Hay referencias oficiales validadas fuera del conjunto seleccionado.",
  documentos_sin_seleccionar: "Hay documentos disponibles fuera del conjunto seleccionado.",
  version_mas_reciente_disponible: "Hay una versión más reciente del documento.",
  documento_no_disponible: "El documento no está disponible para el análisis.",
  extraccion_incompleta: "La extracción falta, está en curso o tiene cobertura insuficiente.",
  limite_texto_fuente: "Se alcanzó el límite de texto. La cobertura es parcial.",
  limite_documentos: "Se alcanzó el límite de documentos.",
  instruccion_documental_omitida: "Se omitió un fragmento con instrucciones ajenas al análisis.",
  cita_invalida: "Se descartó una cita que no coincide con el texto fuente.",
  adaptador_sin_resultado: "El adaptador no entregó un resultado utilizable.",
  posible_contradiccion_adenda: "Posible contradicción entre documentos. Comprueba las dos citas.",
  revisar_precedencia_adendas: "Revisa la precedencia y los cambios introducidos por las adendas.",
  texto_ambiguo: "El texto requiere aclaración.",
  documento_sin_hallazgos: "El adaptador no identificó hallazgos citables en el documento.",
  sin_objeto_confirmado: "Objeto pendiente de revisión.",
  sin_entregable_confirmado: "Entregables pendientes de revisión.",
  sin_plazo_confirmado: "Plazos pendientes de revisión.",
  sin_requisitos_confirmados: "Requisitos pendientes de revisión.",
};
const kinds: Record<Finding["kind"], string> = {
  objeto: "Objeto", entregable: "Entregable", plazo: "Plazo", alerta: "Alerta",
  habilitante: "Habilitante", evaluable: "Evaluable", obligacion: "Obligación de ejecución",
};

function SourceCitation({ citation }: { citation: Citation }) {
  return <figure className="analysis-citation">
    <blockquote>{citation.quote}</blockquote>
    <figcaption>{citation.title} · versión {citation.version} · {formatLocator(citation.locator)}{" "}
      <a href={`#documento-${citation.document_id}`}>Ver documento</a>
    </figcaption>
  </figure>;
}

export function DossierAnalysis({ opportunityId, documents, disabled }: {
  opportunityId: number; documents: DossierDocument[]; disabled: boolean;
}) {
  const [result, setResult] = useState<Analysis>();
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(false);
  async function generate() {
    setRunning(true);
    setError(false);
    setResult(undefined);
    try { setResult(await analyzeDossier(opportunityId)); }
    catch { setError(true); }
    finally { setRunning(false); }
  }
  const selected = documents.filter((doc) => doc.under_review).length;
  return <section className="dossier-analysis" aria-labelledby="analysis-title">
    <h4 id="analysis-title">Resumen y requisitos</h4>
    <p>Versiones seleccionadas para revisión: {selected}.</p>
    <button className="btn btn-s" type="button" disabled={disabled || running}
      onClick={() => void generate()}>{running ? "Generando…" : "Generar resumen y requisitos"}</button>
    {error ? <p role="alert">No se pudo generar el análisis del expediente.</p> : null}
    {result ? <>
      <p role="status">{result.incomplete ? "Expediente incompleto · " : ""}{
        result.status === "revision_manual" ? "Requiere revisión manual" : "Borrador para revisión"
      }</p>
      {result.warnings.length ? <ul aria-label="Advertencias del análisis">
        {result.warnings.map((warning, index) => <li key={index}>
          {descriptions[warning.code] ?? "Revisar el expediente."}
          {warning.documents.map((id) => {
            const doc = documents.find((item) => item.id === id);
            return doc ? <span key={id}> · {doc.title} (versión {doc.version})</span> : null;
          })}
          {warning.citations.map((citation, index) => <SourceCitation key={index} citation={citation} />)}
        </li>)}
      </ul> : null}
      <h5>Resumen</h5>
      {result.summary.map((item, index) => <div key={index}>
        <strong>{kinds[item.kind]}</strong><SourceCitation citation={item.citation} />
      </div>)}
      <h5>Requisitos tipados</h5>
      {result.requirements.map((item, index) => <div key={index}>
        <strong>{kinds[item.kind]}</strong><SourceCitation citation={item.citation} />
      </div>)}
    </> : null}
  </section>;
}
