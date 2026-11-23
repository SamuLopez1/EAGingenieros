import type { OpportunityPage } from "../api/contracts";

export function catalogWarning(page: OpportunityPage, now: number): string | null {
  if (page.latest_sync_outcome === "failed")
    return "La última sincronización falló: los datos pueden estar desactualizados.";
  if (page.latest_sync_outcome === "running")
    return "Hay una sincronización en curso: esta copia puede estar incompleta.";
  if (!page.catalog_synced_at && !page.latest_sync_outcome)
    return "Catálogo nunca sincronizado: no hay cargas ni ejecuciones registradas.";
  if (page.latest_sync_outcome !== "completed")
    return "No hay una sincronización completa confirmada. Verifica la información en SECOP.";
  const stamp = Date.parse(page.catalog_synced_at ?? "");
  if (!Number.isFinite(stamp))
    return "Sincronización correcta, sin fecha de carga disponible para comprobar la antigüedad.";
  const hours = page.catalog_stale_after_hours ?? 24;
  return now - stamp >= hours * 3_600_000
    ? `La última sincronización fue correcta, pero la carga del catálogo tiene al menos ${hours} horas: los datos pueden estar desactualizados.`
    : null;
}
