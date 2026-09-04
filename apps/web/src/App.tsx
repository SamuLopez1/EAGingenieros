import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { browserAuthClient } from "./auth";
import type { AuthClient, SessionState } from "./auth";
import { fetchHealth } from "./health";

type ConnectionState =
  | { kind: "loading" }
  | { kind: "connected"; health: Awaited<ReturnType<typeof fetchHealth>> }
  | { kind: "error" };

const loadingState: ConnectionState = { kind: "loading" };
type AuthViewState = { kind: "loading" } | { kind: "error" } | SessionState;
const loadingAuthState: AuthViewState = { kind: "loading" };

export function App({
  loadHealth = fetchHealth,
  authClient = browserAuthClient,
}: {
  loadHealth?: typeof fetchHealth;
  authClient?: AuthClient;
}) {
  const [connection, setConnection] = useState<ConnectionState>(loadingState);
  const [auth, setAuth] = useState<AuthViewState>(loadingAuthState);
  const [email, setEmail] = useState("");
  const [loginMessage, setLoginMessage] = useState<string | null>(null);

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

  useEffect(() => {
    let active = true;
    authClient
      .loadSession()
      .then((session) => {
        if (active) {
          setAuth(session);
        }
      })
      .catch(() => {
        if (active) {
          setAuth({ kind: "error" });
        }
      });
    return () => {
      active = false;
    };
  }, [authClient]);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginMessage(null);
    try {
      await authClient.requestSignIn(email);
      setLoginMessage("Si tu invitación está vigente, recibirás un enlace de acceso.");
    } catch {
      setLoginMessage("No fue posible solicitar el acceso. Contacta a un administrador.");
    }
  }

  async function signOut() {
    try {
      await authClient.signOut();
      setAuth({ kind: "anonymous" });
    } catch {
      setLoginMessage("No fue posible cerrar la sesión. Inténtalo de nuevo.");
    }
  }

  return (
    <main>
      <h1>EAG Ingenieros</h1>
      <p>Acceso por invitación: sin registro público ni módulos de negocio.</p>
      <section aria-label="Sesión">
        <h2>Sesión</h2>
        {auth.kind === "loading" ? <p role="status">Comprobando sesión…</p> : null}
        {auth.kind === "configuration-required" ? (
          <p role="alert">El inicio de sesión está pendiente de configuración por EAG.</p>
        ) : null}
        {auth.kind === "error" ? <p role="alert">No fue posible comprobar la sesión.</p> : null}
        {auth.kind === "anonymous" ? (
          <form onSubmit={submitLogin}>
            <label htmlFor="email">Correo invitado</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            <button type="submit">Solicitar enlace de acceso</button>
          </form>
        ) : null}
        {auth.kind === "authenticated" ? (
          <div>
            <p>Sesión autenticada.</p>
            <p>Rol asignado por el servidor: {auth.role}.</p>
            <button type="button" onClick={signOut}>
              Cerrar sesión
            </button>
          </div>
        ) : null}
        {loginMessage ? <p role="status">{loginMessage}</p> : null}
      </section>
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
