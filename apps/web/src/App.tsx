import { useEffect, useState } from "react";

import { fetchHealth } from "./health";

type ConnectionState =
  | { kind: "loading" }
  | { kind: "connected"; health: Awaited<ReturnType<typeof fetchHealth>> }
  | { kind: "error" };

const loadingState: ConnectionState = { kind: "loading" };

export function App({ loadHealth = fetchHealth }: { loadHealth?: typeof fetchHealth }) {
  const [connection, setConnection] = useState<ConnectionState>(loadingState);

  useEffect(() => {
    const controller = new AbortController();
    loadHealth(controller.signal)
      .then((health) => setConnection({ kind: "connected", health }))
      .catch(() => {
        if (!controller.signal.aborted) {
          setConnection({ kind: "error" });
        }
      });
    return () => controller.abort();
  }, [loadHealth]);

  return (
    <main>
      <h1>EAG Ingenieros</h1>
      <p>Base técnica inicial: sin módulos de negocio ni decisiones automáticas.</p>
      {connection.kind === "loading" ? <p role="status">Comprobando conexión con la API…</p> : null}
      {connection.kind === "error" ? (
        <p role="alert">No fue posible comprobar la conexión con la API.</p>
      ) : null}
      {connection.kind === "connected" ? (
        <section aria-label="Estado de la API">
          <p>Conexión comprobada.</p>
          <dl>
            <div>
              <dt>Estado</dt>
              <dd>{connection.health.status}</dd>
            </div>
            <div>
              <dt>Versión</dt>
              <dd>{connection.health.version}</dd>
            </div>
            <div>
              <dt>Entorno</dt>
              <dd>{connection.health.environment}</dd>
            </div>
          </dl>
        </section>
      ) : null}
    </main>
  );
}
