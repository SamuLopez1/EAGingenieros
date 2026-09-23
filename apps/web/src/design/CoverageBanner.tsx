/**
 * Declaración de cobertura de fuentes.
 *
 * Existe por una razón concreta: el listado mezcla dos plataformas y una de
 * ellas está parcialmente cubierta. Sin este aviso, el analista leería una
 * tabla ordenada y creería que contiene todo el mercado público. Lo que no está
 * sincronizado se declara; no se deja deducir.
 *
 * El enunciado del aviso es explícito sobre lo que NO se sabe: el solapamiento
 * entre SECOP I y SECOP II no está establecido y la medición disponible no
 * permite afirmar que un proceso esté o no en la otra plataforma.
 */

import type { SourceCoverage } from "../api/contracts";
import { coverageLabel, coverageNeedsWarning } from "./platform";

export function CoverageBanner({ sources }: { sources: SourceCoverage[] }) {
  if (sources.length === 0) return null;

  const warn = sources.filter((source) => coverageNeedsWarning(source.coverage));

  return (
    <section className="coverage" aria-label="Cobertura de fuentes">
      <div className="coverage-head">
        <h2 className="coverage-title">Fuentes sincronizadas</h2>
        {warn.length > 0 ? (
          <span className="coverage-warn">
            Cobertura incompleta en {warn.length === 1 ? "una fuente" : `${warn.length} fuentes`}
          </span>
        ) : null}
      </div>

      <ul className="coverage-list">
        {sources.map((source) => (
          <li key={source.dataset} className="coverage-item">
            <span className="coverage-platform">{source.short_label}</span>
            <span
              className={
                coverageNeedsWarning(source.coverage)
                  ? "coverage-state is-warn"
                  : "coverage-state"
              }
            >
              {coverageLabel(source.coverage)}
            </span>
            <span className="coverage-count tnum">
              {source.opportunity_count.toLocaleString("es-CO")}
            </span>
            <span className="coverage-note">{source.note}</span>
          </li>
        ))}
      </ul>

      <p className="coverage-footnote">
        La relación entre los procesos de SECOP I y los de SECOP II no está
        establecida. Un proceso puede aparecer en ambas plataformas con
        referencias distintas: el sistema lo señala cuando coinciden el NIT y la
        referencia, y no fusiona las filas por su cuenta.
      </p>
    </section>
  );
}
