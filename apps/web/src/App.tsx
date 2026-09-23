/**
 * Aplicación: enrutado y armazón visual.
 *
 * La puerta de sesión envuelve a todas las rutas. Comprobarla en cada página
 * llevaría a olvidarla en alguna; aquí no hay forma de añadir una ruta
 * protegida sin pasar por ella.
 *
 * El armazón es deliberadamente sobrio: una cabecera con la marca, la
 * navegación, el estado del entorno y la sesión. La superficie de trabajo —la
 * tabla de oportunidades— es lo que debe dominar la pantalla, y por eso la
 * cabecera no lleva fondo de color ni compite en peso tipográfico.
 */

import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, Route, Routes, useNavigate } from "react-router-dom";

import { fetchHealth } from "./api/client";
import { useSession } from "./auth/session-context";
import { LoginPage } from "./pages/LoginPage";
import { OpportunityDetailPage } from "./pages/OpportunityDetailPage";
import { OpportunitiesPage } from "./pages/OpportunitiesPage";
import { SourcesPage } from "./pages/SourcesPage";

function EnvironmentChip() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => fetchHealth(signal),
    // El estado del entorno cambia solo al desplegar; no hace falta consultarlo
    // en cada navegación.
    staleTime: 5 * 60_000,
    retry: 1,
  });

  if (!health.data) return null;

  const persistent = health.data.persistence === "database";
  return (
    <span
      className={persistent ? "env env-db" : "env env-mem"}
      title={
        persistent
          ? "Los datos se conservan en base de datos."
          : "Modo memoria: los datos se pierden al reiniciar la API."
      }
    >
      {persistent ? "Base de datos" : "Modo memoria"}
    </span>
  );
}

function AppShell() {
  const { user, signOut } = useSession();
  const navigate = useNavigate();

  return (
    <>
      <header className="top">
        <div className="wrap top-in">
          <NavLink to="/" className="brand">
            <span className="mark" aria-hidden="true" />
            EAG · Licitaciones
          </NavLink>

          <nav className="top-nav" aria-label="Navegación principal">
            <NavLink to="/" end>
              Oportunidades
            </NavLink>
            <NavLink to="/fuentes">Fuentes</NavLink>
          </nav>

          <div className="top-right">
            <EnvironmentChip />
            {user ? (
              <span className="who" title={user.email}>
                {user.display_name || user.email}
                <span className="who-role">{user.role}</span>
              </span>
            ) : null}
            <button
              type="button"
              className="btn btn-s"
              onClick={() => {
                // `void` evita una promesa sin manejar; el proveedor ya
                // gestiona el estado de la sesión.
                void signOut().then(() => navigate("/login", { replace: true }));
              }}
            >
              Salir
            </button>
          </div>
        </div>
      </header>

      <Outlet />
    </>
  );
}

function SessionGate() {
  const { status } = useSession();

  if (status === "loading") {
    return (
      <main className="wrap">
        <div className="empty">
          <p className="empty-title">Comprobando la sesión…</p>
        </div>
      </main>
    );
  }

  if (status === "anonymous") return <LoginPage />;
  return <AppShell />;
}

export function App() {
  return (
    <Routes>
      <Route element={<SessionGate />}>
        <Route path="/" element={<OpportunitiesPage />} />
        <Route path="/oportunidades/:id" element={<OpportunityDetailPage />} />
        <Route path="/fuentes" element={<SourcesPage />} />
        {/* Una ruta desconocida no debe dejar la pantalla en blanco. */}
        <Route path="*" element={<OpportunitiesPage />} />
      </Route>
    </Routes>
  );
}
