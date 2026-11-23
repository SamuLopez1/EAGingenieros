import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const provider = vi.hoisted(() => {
  vi.stubEnv("VITE_SUPABASE_URL", "https://example.supabase.co");
  vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", "synthetic-public-key");
  vi.stubEnv("VITE_API_BASE_URL", "");
  let notify = () => {};
  let signedIn = false;
  let credentialsCorrect = false;
  return {
    credentialsCorrect: () => credentialsCorrect,
    auth: {
      onAuthStateChange: (callback: () => void) => {
        notify = callback;
        return { data: { subscription: { unsubscribe: () => { notify = () => {}; } } } };
      },
      signInWithPassword: async ({ email, password }: { email: string; password: string }) => {
        credentialsCorrect = email === "user@example.com" && password === "<INVALID_PASSWORD_PLACEHOLDER>";
        signedIn = true;
        notify();
        return { error: null };
      },
      getSession: async () => ({
        data: { session: signedIn ? {
          access_token: "synthetic-access",
          user: { user_metadata: { role: "administrador" } },
        } : null }, error: null,
      }),
      signOut: async () => { signedIn = false; notify(); return { error: null }; },
    },
  };
});
vi.mock("@supabase/supabase-js", () => ({ createClient: () => ({ auth: provider.auth }) }));

import { App } from "./App";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

it("offline flow: password to Supabase, bearer to API, server role to UI, then logout", async () => {
  const logs = ["log", "info", "warn", "error", "debug"] as const;
  const spies = logs.map((method) => vi.spyOn(console, method).mockImplementation(() => {}));
  const api = vi.fn(async (url: string, options?: RequestInit) => {
    // Only booleans can appear in failed assertions; never dump captured requests.
    expect(JSON.stringify([url, options]).includes("INVALID_PASSWORD_PLACEHOLDER")).toBe(false);
    expect(options?.body === undefined).toBe(true);
    if (url === "/api/health") {
      return new Response(JSON.stringify({ status: "ok", version: "test", environment: "test" }));
    }
    expect(url === "/api/auth/session").toBe(true);
    expect(new Headers(options?.headers).get("Authorization") === "Bearer synthetic-access").toBe(true);
    return new Response(JSON.stringify({ organization_id: "synthetic", role: "analista" }));
  });
  vi.stubGlobal("fetch", api);
  render(<App />);
  await screen.findByRole("button", { name: "Iniciar sesión" });
  fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "user@example.com" } });
  fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "<INVALID_PASSWORD_PLACEHOLDER>" } });
  expect(document.body.innerHTML.includes("INVALID_PASSWORD_PLACEHOLDER")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Iniciar sesión" }));
  expect(await screen.findByText("Rol asignado por el servidor: analista.")).toBeInTheDocument();
  expect(provider.credentialsCorrect()).toBe(true);
  expect(api.mock.calls.some(([url]) => url === "/api/auth/session")).toBe(true);
  expect(document.body.innerHTML.includes("INVALID_PASSWORD_PLACEHOLDER")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));
  await screen.findByRole("button", { name: "Iniciar sesión" });
  expect(screen.getByLabelText("Contraseña")).toHaveValue("");
  expect(screen.queryByText("Sesión autenticada.")).not.toBeInTheDocument();
  expect(spies.some((spy) => spy.mock.calls.length > 0)).toBe(false);
});
