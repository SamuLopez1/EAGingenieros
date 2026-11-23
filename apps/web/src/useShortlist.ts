import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./api/client";
import { fetchShortlist, putShortlist } from "./api/shortlist";
import type { Shortlist } from "./api/shortlist";

export function useShortlist() {
  const [data, setData] = useState<Shortlist>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchShortlist(controller.signal).then(
      (saved) => { if (!controller.signal.aborted) setData(saved); },
      () => { if (!controller.signal.aborted) setMessage("No se pudo cargar la lista corta."); },
    );
    return () => controller.abort();
  }, [revision]);

  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  async function toggle(id: number) {
    if (!data || busy) return;
    const ids = data.items.map((item) => item.id);
    const next = ids.includes(id) ? ids.filter((existing) => existing !== id) : [...ids, id];
    if (next.length > 3) {
      setMessage("Quita una oportunidad para agregar otra. El máximo es tres.");
      return;
    }
    setMessage("");
    setBusy(true);
    try { setData(await putShortlist(data.revision, next)); }
    catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setMessage("La lista cambió en otra sesión. Revisa la selección actual.");
        refresh();
      } else setMessage("No se pudo guardar el cambio en la lista.");
    } finally { setBusy(false); }
  }

  return { data, busy, message, refresh, toggle };
}
