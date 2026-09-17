/**
 * Formateo de valores para la interfaz.
 *
 * Regla del sistema de diseño: un dato desconocido no es cero. Se muestra como
 * guion explícito en gris. Rellenar con `0` o dejar la celda vacía haría creer
 * que el dato existe y vale cero, y en una comparación de requisitos esa
 * diferencia cambia el veredicto.
 */

/** Marcador explícito de valor desconocido. */
export const UNKNOWN = "—";

export function formatDate(value: string | null | undefined): string {
  if (!value) return UNKNOWN;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return UNKNOWN;
  // Formato ISO corto: se ordena bien como texto y no depende del locale del
  // navegador, que en una tabla ordenable produciría lecturas inconsistentes.
  return parsed.toISOString().slice(0, 10);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return UNKNOWN;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return UNKNOWN;
  return `${parsed.toISOString().slice(0, 10)} ${parsed
    .toISOString()
    .slice(11, 16)}`;
}

export function formatText(value: string | null | undefined): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : UNKNOWN;
}

/** Indica si el valor es desconocido, para aplicar el estilo atenuado. */
export function isUnknown(value: string | null | undefined): boolean {
  return !value || !value.trim();
}

/** Fecha relativa en días, para señalar datos desactualizados. */
export function daysSince(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  const diff = Date.now() - parsed.getTime();
  return Math.floor(diff / 86_400_000);
}

/**
 * Antigüedad de la última sincronización.
 *
 * Se declara explícitamente cuando el dato es viejo en lugar de mostrar la
 * fecha sin más: una tabla de oportunidades desactualizada parece completa, y
 * el analista tomaría decisiones sobre un catálogo que ya no refleja SECOP.
 */
export function staleness(
  value: string | null | undefined,
): { label: string; stale: boolean } {
  const days = daysSince(value);
  if (days === null) return { label: "sin sincronizar", stale: true };
  if (days <= 0) return { label: "hoy", stale: false };
  if (days === 1) return { label: "ayer", stale: false };
  if (days <= 7) return { label: `hace ${days} días`, stale: false };
  return { label: `hace ${days} días`, stale: true };
}
