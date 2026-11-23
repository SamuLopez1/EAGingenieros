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

export function formatColombiaDateTime(value: string | null | undefined): string {
  if (!value) return UNKNOWN;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return UNKNOWN;
  return new Intl.DateTimeFormat("es-CO", {
    timeZone: "America/Bogota",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(parsed);
}

export function formatText(value: string | null | undefined): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : UNKNOWN;
}

/** Indica si el valor es desconocido, para aplicar el estilo atenuado. */
export function isUnknown(value: string | null | undefined): boolean {
  return !value || !value.trim();
}

export function officialSecopUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    const official = ["secop.gov.co", "colombiacompra.gov.co"].some(
      (domain) => url.hostname === domain || url.hostname.endsWith(`.${domain}`),
    );
    return url.protocol === "https:" && official && !url.username && !url.password
      ? url.href : null;
  } catch {
    return null;
  }
}
