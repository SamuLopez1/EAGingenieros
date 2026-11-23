import { useEffect, useState } from "react";
import type { OpportunityPage } from "../api/contracts";
import { formatColombiaDateTime } from "./format";
import { catalogWarning } from "./catalogAge";

export function CatalogFreshness({ page }: { page: OpportunityPage }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const warning = catalogWarning(page, now);
  return (
    <div className="catalog-freshness">
      <p>
        Última carga del catálogo (hora Colombia):{" "}
        <strong>{formatColombiaDateTime(page.catalog_synced_at)}</strong>. No es la fecha de
        publicación.
      </p>
      <p>
        Última sincronización finalizada (hora Colombia):{" "}
        {formatColombiaDateTime(page.latest_sync_finished_at)}. Umbral de antigüedad:{" "}
        {page.catalog_stale_after_hours ?? 24} horas (configuración técnica provisional, pendiente
        de validación con EAG).
      </p>
      {warning ? (
        <p className="banner banner-warn" role="status">
          {warning}
        </p>
      ) : null}
    </div>
  );
}
