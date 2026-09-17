import type { ComparisonState } from "../api/contracts";

/**
 * Etiquetas y significados de los estados de comparación.
 *
 * Viven fuera del componente para que el módulo de React solo exporte
 * componentes (regla `react-refresh/only-export-components`) y para que las
 * pruebas puedan verificar los textos sin montar la interfaz.
 *
 * Regla del sistema de diseño: el color nunca es la única señal. Todo estado
 * lleva su etiqueta de texto, porque alrededor del 8 % de los hombres tiene
 * alguna deficiencia de visión cromática y esta interfaz decide si se participa
 * en una licitación.
 */

export const STATE_LABELS: Record<ComparisonState, string> = {
  cumple: "Cumple",
  cumple_parcialmente: "Cumple parcialmente",
  no_cumple: "No cumple",
  revision_manual: "Revisión manual",
};

/** Significado de cada estado, expuesto como título accesible. */
export const STATE_MEANINGS: Record<ComparisonState, string> = {
  cumple:
    "Requisito satisfecho con evidencia suficiente, vigente y compatible.",
  cumple_parcialmente:
    "Requisito divisible satisfecho en parte, bajo criterio validado.",
  no_cumple: "Incumplimiento demostrado.",
  revision_manual:
    "No evaluable: falta evidencia, es ambigua o ilegible. No implica incumplimiento.",
};

export const STATE_CLASS: Record<ComparisonState, string> = {
  cumple: "state state-met",
  cumple_parcialmente: "state state-partial",
  no_cumple: "state state-unmet",
  revision_manual: "state state-review",
};

export const stateLabel = (state: ComparisonState): string =>
  STATE_LABELS[state];

export const stateMeaning = (state: ComparisonState): string =>
  STATE_MEANINGS[state];
