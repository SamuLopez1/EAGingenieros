import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { SessionCheckError } from "./auth";
import type { AuthClient, SessionState } from "./auth";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("shows a later successful login without remounting", async () => {
    let changed = () => {};
    const authClient: AuthClient = {
      onSessionChange: (listener) => { changed = listener; return () => {}; },
      loadSession: vi.fn().mockResolvedValueOnce({ kind: "anonymous" })
        .mockResolvedValue({ kind: "authenticated", organizationId: "synthetic", role: "analista" }),
      requestSignIn: vi.fn(), signOut: vi.fn(),
    };
    render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);
    await screen.findByRole("button", { name: "Solicitar enlace de acceso" });
    act(() => changed());
    expect(await screen.findByText("Sesión autenticada.")).toBeInTheDocument();
  });

  it("explains a permission denial and permits logout", async () => {
    const authClient: AuthClient = {
      onSessionChange: () => () => {},
      loadSession: async () => { throw new SessionCheckError(403); },
      requestSignIn: vi.fn(), signOut: vi.fn().mockResolvedValue(undefined),
    };
    render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);
    expect(await screen.findByText(/La API denegó el acceso \(403\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));
    expect(await screen.findByRole("button", { name: "Solicitar enlace de acceso" })).toBeInTheDocument();
  });

  it("updates after a later auth event and ignores an older permission response", async () => {
    let changed = () => {};
    let finishOldRequest!: (session: SessionState) => void;
    const unsubscribe = vi.fn();
    const authClient = {
      loadSession: vi.fn()
        .mockResolvedValueOnce({ kind: "anonymous" })
        .mockImplementationOnce(() => new Promise<SessionState>((resolve) => { finishOldRequest = resolve; }))
        .mockResolvedValueOnce({ kind: "anonymous" }),
      onSessionChange: (listener: () => void) => { changed = listener; return unsubscribe; },
      requestSignIn: vi.fn(),
      signOut: vi.fn(),
    };
    const { unmount } = render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);
    await screen.findByRole("button", { name: "Solicitar enlace de acceso" });
    act(() => changed());
    await vi.waitFor(() => expect(authClient.loadSession).toHaveBeenCalledTimes(2));
    act(() => changed());
    await screen.findByRole("button", { name: "Solicitar enlace de acceso" });
    await act(async () => finishOldRequest({ kind: "authenticated", organizationId: "synthetic", role: "analista" }));
    expect(screen.queryByText("Sesión autenticada.")).not.toBeInTheDocument();
    unmount();
    expect(unsubscribe).toHaveBeenCalledOnce();
  });
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
      onSessionChange: () => () => {},
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
      onSessionChange: () => () => {},
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
      onSessionChange: () => () => {},
      loadSession: async () => ({ kind: "configuration-required" }),
      requestSignIn: vi.fn(),
      signOut: vi.fn(),
    };
    render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);

    expect(await screen.findByText(/pendiente de configuración por EAG/)).toBeInTheDocument();
    expect(screen.queryByText(/service_role/i)).not.toBeInTheDocument();
  });
});
