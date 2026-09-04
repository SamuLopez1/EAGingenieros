import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type { AuthClient } from "./auth";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the initial loading state", () => {
    render(<App loadHealth={() => new Promise(() => undefined)} />);

    expect(screen.getByText("Comprobando conexión con la API…")).toBeInTheDocument();
  });

  it("renders a successful API health response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok", version: "0.1.0", environment: "test" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    expect(await screen.findByText("Conexión comprobada.")).toBeInTheDocument();
    expect(screen.getByText("0.1.0")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/health",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });

  it("renders an error when the API request fails", async () => {
    render(<App loadHealth={async () => Promise.reject(new Error("offline"))} />);

    expect(await screen.findByText("No fue posible comprobar la conexión con la API.")).toBeInTheDocument();
  });

  it("shows an invite-only login and never a public registration action", async () => {
    const authClient: AuthClient = {
      loadSession: async () => ({ kind: "anonymous" }),
      requestSignIn: vi.fn().mockResolvedValue(undefined),
      signOut: vi.fn(),
    };
    render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);

    expect(await screen.findByRole("button", { name: "Solicitar enlace de acceso" })).toBeInTheDocument();
    expect(screen.queryByText(/registrarse/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Correo invitado"), { target: { value: "user@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Solicitar enlace de acceso" }));

    expect(authClient.requestSignIn).toHaveBeenCalledWith("user@example.com");
    expect(await screen.findByText(/Si tu invitación está vigente/)).toBeInTheDocument();
  });

  it("shows the server-assigned role and allows logout", async () => {
    const authClient: AuthClient = {
      loadSession: async () => ({
        kind: "authenticated",
        organizationId: "00000000-0000-0000-0000-000000000001",
        role: "analista",
      }),
      requestSignIn: vi.fn(),
      signOut: vi.fn().mockResolvedValue(undefined),
    };
    render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);

    expect(await screen.findByText("Rol asignado por el servidor: analista.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    expect(authClient.signOut).toHaveBeenCalledOnce();
    expect(await screen.findByRole("button", { name: "Solicitar enlace de acceso" })).toBeInTheDocument();
  });

  it("identifies an unavailable Supabase configuration without exposing a secret", async () => {
    const authClient: AuthClient = {
      loadSession: async () => ({ kind: "configuration-required" }),
      requestSignIn: vi.fn(),
      signOut: vi.fn(),
    };
    render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);

    expect(await screen.findByText(/pendiente de configuración por EAG/)).toBeInTheDocument();
    expect(screen.queryByText(/service_role/i)).not.toBeInTheDocument();
  });
});
