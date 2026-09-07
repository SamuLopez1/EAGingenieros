import { createClient } from "@supabase/supabase-js";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");
const sessionUrl = `${configuredBaseUrl ?? "/api"}/auth/session`;

export type SessionState =
  | { kind: "configuration-required" }
  | { kind: "anonymous" }
  | { kind: "authenticated"; organizationId: string; role: "administrador" | "analista" };

export interface AuthClient {
  loadSession(): Promise<SessionState>;
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

// Supabase redirige los enlaces de invitación y de acceso a esta UI. El
// navegador debe consumir el callback para poder entregar el JWT a la API.
export const browserAuthClientOptions = {
  auth: { autoRefreshToken: false, persistSession: false, detectSessionInUrl: true },
} as const;

const unavailableAuthClient: AuthClient = {
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
        throw new Error("No fue posible comprobar los permisos de la sesión.");
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

export const browserAuthClient = createBrowserAuthClient();
