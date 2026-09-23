/**
 * Contexto de sesión.
 *
 * El contexto y el hook viven aquí, separados del componente proveedor, para
 * que el módulo del componente solo exporte componentes (regla
 * `react-refresh/only-export-components`) y para poder probar el hook sin
 * montar la interfaz completa.
 */

import { createContext, useContext } from "react";

import type { SessionUser } from "../api/contracts";

export type SessionStatus = "loading" | "authenticated" | "anonymous";

export interface SessionValue {
  user: SessionUser | null;
  status: SessionStatus;
  /** Mensaje del último fallo de acceso, para mostrarlo en el formulario. */
  error: string | null;
  busy: boolean;
  signIn: (email: string, password: string) => Promise<boolean>;
  signOut: () => Promise<void>;
  clearError: () => void;
}

export const SessionContext = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (value === null) {
    throw new Error("useSession requiere <SessionProvider> como ancestro");
  }
  return value;
}
