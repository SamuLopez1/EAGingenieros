/**
 * Procedencia: plataformas y cobertura declarada.
 *
 * Vive fuera de los componentes para que los módulos de React solo exporten
 * componentes (regla `react-refresh/only-export-components`) y para que las
 * pruebas verifiquen los textos sin montar la interfaz.
 *
 * Regla del sistema de diseño que se aplica aquí: el color nunca es la única
 * señal. Cada plataforma y cada estado de cobertura llevan su etiqueta de
 * texto, porque esta interfaz se usa para decidir si se participa en una
 * licitación pública.
 */

import type { CoverageState, Platform } from "../api/contracts";

/** Etiqueta corta y estable por plataforma. */
export const PLATFORM_LABELS: Record<Platform, string> = {
  SECOP_I: "SECOP I",
  SECOP_II: "SECOP II",
};

/**
 * Significado de cada plataforma, expuesto como título accesible.
 *
 * La distinción importa para el analista: SECOP II es la plataforma
 * transaccional vigente y SECOP I la anterior, todavía con publicación
 * reciente. No son intercambiables.
 */
export const PLATFORM_MEANINGS: Record<Platform, string> = {
  SECOP_I:
    "Plataforma anterior de contratación pública. Sigue publicando procesos, pero su solapamiento con SECOP II no está establecido.",
  SECOP_II:
    "Plataforma transaccional vigente. Es la fuente principal del listado.",
};

/**
 * Texto de cobertura declarada.
 *
 * Nunca dice «completo»: lo que no está sincronizado se declara como no
 * sincronizado, en lugar de dejar creer que el listado cubre todo el mercado
 * público.
 */
export const COVERAGE_LABELS: Record<CoverageState, string> = {
  sincronizada: "Sincronizada",
  parcial: "Cobertura parcial",
  historica: "Solo contexto histórico",
  no_sincronizada: "No sincronizada",
};

export const COVERAGE_MEANINGS: Record<CoverageState, string> = {
  sincronizada:
    "Se ingiere de forma continua. Aun así, no garantiza cobertura completa del mercado.",
  parcial:
    "Se ingiere con límites conocidos. Pueden faltar procesos o aparecer el mismo proceso con referencias distintas.",
  historica:
    "Se usa como contexto de contratación, no produce oportunidades en el listado.",
  no_sincronizada: "Declarada pero no ingerida. No aporta filas al listado.",
};

export const coverageLabel = (value: CoverageState): string =>
  COVERAGE_LABELS[value] ?? value;

export const platformLabel = (value: Platform): string =>
  PLATFORM_LABELS[value] ?? value;

/** Indica si la cobertura merece una advertencia visual. */
export function coverageNeedsWarning(value: CoverageState): boolean {
  return value === "parcial" || value === "no_sincronizada";
}
