import { createClient } from "@supabase/supabase-js";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/$/, "") || undefined;
const sessionUrl = `${configuredBaseUrl ?? "/api"}/auth/session`;

export type SessionState =
  | { kind: "configuration-required" }
  | { kind: "anonymous" }
  | { kind: "authenticated"; organizationId: string; role: "administrador" | "analista" };

export interface AuthClient {
  loadSession(): Promise<SessionState>;
  onSessionChange(listener: () => void): () => void;
  requestSignIn(email: string): Promise<void>;
  signOut(): Promise<void>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isSessionPayload(value: unknown): value is {
  organization_id: string;
  role: "administrador" | "analista";
} {
  return (
    isRecord(value) &&
    typeof value.organization_id === "string" &&
    (value.role === "administrador" || value.role === "analista")
  );
}

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabasePublishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

// Este es un cliente de navegador: debe consumir el callback y conservar la
// sesión tras la redirección para poder entregar el JWT a la API. No contiene
// ni puede acceder a una clave de servicio.
export const browserAuthClientOptions = {
  auth: { autoRefreshToken: true, persistSession: true, detectSessionInUrl: true },
} as const;

const unavailableAuthClient: AuthClient = {
  onSessionChange() { return () => {}; },
  async loadSession() {
    return { kind: "configuration-required" };
  },
  async requestSignIn() {
    throw new Error("La autenticación no está configurada.");
  },
  async signOut() {
    return undefined;
  },
};

export function createBrowserAuthClient(): AuthClient {
  if (!supabaseUrl || !supabasePublishableKey) {
    return unavailableAuthClient;
  }

  const supabase = createClient(supabaseUrl, supabasePublishableKey, browserAuthClientOptions);

  return {
    onSessionChange(listener) {
      // El listener solo invalida la vista; las llamadas async se difieren en App.
      const { data } = supabase.auth.onAuthStateChange(() => listener());
      return () => data.subscription.unsubscribe();
    },
    async loadSession() {
      const { data, error } = await supabase.auth.getSession();
      if (error) {
        throw new Error("No fue posible recuperar la sesión.");
      }
      if (!data.session) {
        return { kind: "anonymous" };
      }

      const response = await fetch(sessionUrl, {
        headers: { Accept: "application/json", Authorization: `Bearer ${data.session.access_token}` },
      });
      if (!response.ok) {
        throw new SessionCheckError(response.status);
      }
      const payload: unknown = await response.json();
      if (!isSessionPayload(payload)) {
        throw new Error("La respuesta de sesión no coincide con el contrato publicado.");
      }
      return {
        kind: "authenticated",
        organizationId: payload.organization_id,
        role: payload.role,
      };
    },
    async requestSignIn(email: string) {
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: { emailRedirectTo: window.location.origin, shouldCreateUser: false },
      });
      if (error) {
        throw new Error("No fue posible solicitar el enlace de acceso.");
      }
    },
    async signOut() {
      const { error } = await supabase.auth.signOut();
      if (error) {
        throw new Error("No fue posible cerrar la sesión.");
      }
    },
  };
}

export class SessionCheckError extends Error {
  constructor(readonly status: number) {
    // Solo mensajes locales: nunca propagar cuerpos o errores del proveedor.
    super(status === 401
      ? "La API rechazó la sesión (401). Solicita un nuevo enlace o contacta a un administrador."
      : status === 403
        ? "La API denegó el acceso (403). Contacta a un administrador para revisar tu pertenencia a EAG."
        : status === 503
          ? "La verificación de acceso no está disponible (503). Contacta a un administrador."
          : "No fue posible comprobar la sesión.");
  }
}

export const browserAuthClient = createBrowserAuthClient();
