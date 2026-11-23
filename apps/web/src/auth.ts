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
  signIn(email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
  getAccessToken?(): Promise<string | null>;
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
  async signIn() {
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
    async getAccessToken() {
      const { data, error } = await supabase.auth.getSession();
      if (error) throw new Error("El proveedor de acceso no está disponible.");
      return data.session?.access_token ?? null;
    },
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
    async signIn(email: string, password: string) {
      try {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw new Error();
      } catch {
        // No propagar mensajes/cause del proveedor ni distinguir cuentas existentes.
        throw new Error(signInErrorMessage);
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
    super(status === 401 || status === 403
      ? "No fue posible autorizar el acceso. Contacta a un administrador."
      : status === 503
        ? "La verificación de acceso no está disponible. Inténtalo de nuevo más tarde."
        : "No fue posible comprobar la sesión.");
  }
}

export const signInErrorMessage = "No fue posible iniciar sesión. Revisa tus credenciales e inténtalo de nuevo.";

export const browserAuthClient = createBrowserAuthClient();
