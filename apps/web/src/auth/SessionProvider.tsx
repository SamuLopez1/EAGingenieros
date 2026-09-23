/**
 * Proveedor de sesión.
 *
 * Al arrancar no basta con que haya tokens en el almacenamiento: se consulta
 * `/api/v1/auth/session` para que el servidor confirme que la sesión sigue
 * vigente. Un token guardado puede estar revocado —cambio de contraseña,
 * cierre de sesión en otro equipo, revocación por reutilización— y mostrar la
 * interfaz como si hubiera sesión llevaría al usuario a una pantalla que falla
 * en cada petición sin explicar por qué.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, fetchSession, login, logout, setSessionExpiredHandler } from "../api/client";
import type { SessionUser } from "../api/contracts";
import { clearTokens, hasSession, loadTokens } from "./tokens";
import { SessionContext, type SessionStatus, type SessionValue } from "./session-context";

loadTokens();

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [status, setStatus] = useState<SessionStatus>(() =>
    hasSession() ? "loading" : "anonymous",
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Cuando el cliente HTTP no logra refrescar la sesión, avisa aquí para
  // volver al acceso. Sin este enlace, la interfaz se quedaría mostrando un
  // panel vacío con errores repetidos en lugar de pedir credenciales.
  useEffect(() => {
    setSessionExpiredHandler(() => {
      setUser(null);
      setStatus("anonymous");
      setError("La sesión caducó. Vuelva a iniciar sesión.");
    });
    return () => setSessionExpiredHandler(null);
  }, []);

  useEffect(() => {
    if (!hasSession()) return;
    const controller = new AbortController();
    let active = true;

    fetchSession(controller.signal)
      .then((session) => {
        if (!active) return;
        setUser({
          user_id: session.user_id,
          email: session.email,
          display_name: session.display_name,
          role: session.role,
        });
        setStatus("authenticated");
      })
      .catch((failure: unknown) => {
        if (!active) return;
        clearTokens();
        setUser(null);
        setStatus("anonymous");
        // Un fallo de red no es lo mismo que una sesión inválida; se distingue
        // para no decirle al usuario que su sesión caducó cuando el problema
        // es que la API no responde.
        setError(
          failure instanceof ApiError && failure.isUnauthorized
            ? null
            : "No fue posible comprobar la sesión con la API.",
        );
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    setBusy(true);
    setError(null);
    try {
      const tokens = await login(email, password);
      setUser(tokens.user);
      setStatus("authenticated");
      return true;
    } catch (failure) {
      const message =
        failure instanceof ApiError
          ? failure.status === 401
            ? "Correo o contraseña incorrectos."
            : failure.status === 503
              ? "La autenticación no está configurada en el servidor."
              : failure.message
          : "No fue posible contactar la API.";
      setError(message);
      setStatus("anonymous");
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    setBusy(true);
    try {
      await logout();
    } finally {
      setUser(null);
      setStatus("anonymous");
      setError(null);
      setBusy(false);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  const value = useMemo<SessionValue>(
    () => ({ user, status, error, busy, signIn, signOut, clearError }),
    [user, status, error, busy, signIn, signOut, clearError],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
