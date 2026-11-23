import { lazy, Suspense, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { browserAuthClient, SessionCheckError, signInErrorMessage } from "./auth";
import type { AuthClient, SessionState } from "./auth";
import { fetchHealth } from "./health";

const OpportunitiesPage = lazy(() => import("./OpportunitiesPage"));
const CompanyProfile = lazy(() => import("./CompanyProfile"));

type ConnectionState =
  | { kind: "loading" }
  | { kind: "connected"; health: Awaited<ReturnType<typeof fetchHealth>> }
  | { kind: "error" };

const loadingState: ConnectionState = { kind: "loading" };
type AuthViewState = { kind: "loading" } | { kind: "error"; message: string } | SessionState;
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
  const passwordInput = useRef<HTMLInputElement>(null);
  const [signingIn, setSigningIn] = useState(false);
  const [loginMessage, setLoginMessage] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [showProfile, setShowProfile] = useState(false);

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
    let revision = 0;
    let timer: ReturnType<typeof setTimeout>;
    function refresh() {
      const current = ++revision;
      clearTimeout(timer);
      setAuth(loadingAuthState);
      // Salir del callback de Supabase antes de invocar métodos de Auth.
      timer = setTimeout(() => {
        authClient.loadSession().then((session) => {
          if (active && current === revision) setAuth(session);
        }).catch((error: unknown) => {
          if (active && current === revision) {
            setAuth({ kind: "error", message: error instanceof SessionCheckError
              ? error.message : "No fue posible comprobar la sesión." });
          }
        });
      }, 0);
    }
    const unsubscribe = authClient.onSessionChange(refresh);
    refresh();
    return () => {
      active = false;
      clearTimeout(timer);
      unsubscribe();
    };
  }, [authClient, retry]);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (signingIn) return;
    setLoginMessage(null);
    const password = passwordInput.current?.value ?? "";
    // Campo no controlado: no copiar la contraseña a estado, HTML o mensajes.
    if (passwordInput.current) passwordInput.current.value = "";
    setSigningIn(true);
    try {
      await authClient.signIn(email, password);
    } catch {
      setLoginMessage(signInErrorMessage);
    } finally {
      setSigningIn(false);
    }
  }

  async function signOut() {
    try {
      await authClient.signOut();
      setLoginMessage(null);
      setAuth({ kind: "anonymous" });
      setShowProfile(false);
    } catch {
      setLoginMessage("No fue posible cerrar la sesión. Inténtalo de nuevo.");
    }
  }

  if (auth.kind === "authenticated") {
    return (
      <div className="workspace-shell">
        <nav className="session-bar" aria-label="Cuenta">
          <span>Sesión autenticada.</span>
          <span>Rol asignado por el servidor: {auth.role}.</span>
          <button type="button" onClick={() => setShowProfile((value) => !value)}>
            {showProfile ? "Volver a oportunidades" : "Perfil empresarial"}
          </button>
          <button type="button" onClick={signOut}>Cerrar sesión</button>
        </nav>
        {loginMessage ? <p role="status">{loginMessage}</p> : null}
        <Suspense fallback={<p role="status">Cargando catálogo…</p>}>
          {showProfile ? <CompanyProfile key={auth.organizationId} editable={auth.role === "administrador"} />
            : <OpportunitiesPage key={auth.organizationId} role={auth.role} />}
        </Suspense>
      </div>
    );
  }

  return (
    <main className="auth-screen">
      <h1>EAG Ingenieros</h1>
      <p>Consulta y seguimiento de oportunidades de contratación pública.</p>
      <p>Acceso por invitación, sin registro público.</p>
      <section aria-label="Sesión">
        <h2>Sesión</h2>
        {auth.kind === "loading" ? <p role="status">Comprobando sesión…</p> : null}
        {auth.kind === "configuration-required" ? (
          <p role="alert">El inicio de sesión está pendiente de configuración por EAG.</p>
        ) : null}
        {auth.kind === "error" ? (
          <div>
            <p role="alert">{auth.message}</p>
            <button type="button" onClick={signOut}>Cerrar sesión</button>
            <button type="button" onClick={() => setRetry((value) => value + 1)}>Reintentar conexión</button>
          </div>
        ) : null}
        {auth.kind === "anonymous" ? (
          <form onSubmit={submitLogin}>
            <label htmlFor="email">Correo</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            <label htmlFor="password">Contraseña</label>
            <input
              ref={passwordInput}
              id="password"
              type="password"
              autoComplete="current-password"
              required
            />
            <button type="submit" disabled={signingIn}>
              {signingIn ? "Iniciando sesión…" : "Iniciar sesión"}
            </button>
          </form>
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
