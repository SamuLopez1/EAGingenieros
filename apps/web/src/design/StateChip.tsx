import type { ComparisonState } from "../api/contracts";
import { STATE_CLASS, STATE_MEANINGS, STATE_LABELS } from "./states";

/**
 * Chip de veredicto.
 *
 * Muestra siempre la etiqueta de texto además del color: el color nunca es la
 * única señal. `revision_manual` es gris, nunca rojo — la ausencia de evidencia
 * no es incumplimiento, y pintarla de rojo haría leer un fallo donde solo hay
 * información pendiente.
 */
export function StateChip({
  state,
  count,
}: {
  state: ComparisonState;
  count?: number;
}) {
  return (
    <span className={STATE_CLASS[state]} title={STATE_MEANINGS[state]}>
      <span className="state-dot" aria-hidden="true" />
      {STATE_LABELS[state]}
      {typeof count === "number" ? (
        <span className="state-count tnum">{count}</span>
      ) : null}
    </span>
  );
}
