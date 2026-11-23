import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { SessionCheckError } from "./auth";
import type { AuthClient, SessionState } from "./auth";

vi.mock("./OpportunitiesPage", () => ({ default: () => <div>Catálogo conectado</div> }));

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
      signIn: vi.fn(), signOut: vi.fn(),
    };
    render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);
    await screen.findByRole("button", { name: "Iniciar sesión" });
    act(() => changed());
    expect(await screen.findByText("Sesión autenticada.")).toBeInTheDocument();
  });

  it("explains a permission denial and permits logout", async () => {
    const authClient: AuthClient = {
      onSessionChange: () => () => {},
      loadSession: async () => { throw new SessionCheckError(403); },
      signIn: vi.fn(), signOut: vi.fn().mockResolvedValue(undefined),
    };
    render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);
    expect(await screen.findByText(/No fue posible autorizar el acceso/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));
    expect(await screen.findByRole("button", { name: "Iniciar sesión" })).toBeInTheDocument();
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
      signIn: vi.fn(),
      signOut: vi.fn(),
    };
    const { unmount } = render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);
    await screen.findByRole("button", { name: "Iniciar sesión" });
    act(() => changed());
    await vi.waitFor(() => expect(authClient.loadSession).toHaveBeenCalledTimes(2));
    act(() => changed());
    await screen.findByRole("button", { name: "Iniciar sesión" });
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

  it("shows password login with no registration and clears the password on submit", async () => {
    const authClient: AuthClient = {
      onSessionChange: () => () => {},
      loadSession: async () => ({ kind: "anonymous" }),
      signIn: vi.fn().mockResolvedValue(undefined),
      signOut: vi.fn(),
    };
    render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);

    expect(await screen.findByRole("button", { name: "Iniciar sesión" })).toBeInTheDocument();
    expect(screen.getByText(/sin registro público/)).toBeInTheDocument();
    expect(screen.queryByText(/registrarse/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/recuperar contraseña/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "user@example.com" } });
    const password = screen.getByLabelText("Contraseña");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autoComplete", "current-password");
    fireEvent.change(password, { target: { value: "<INVALID_PASSWORD_PLACEHOLDER>" } });
    expect(document.body.innerHTML.includes("<INVALID_PASSWORD_PLACEHOLDER>")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Iniciar sesión" }));

    expect(authClient.signIn).toHaveBeenCalledOnce();
    expect(password).toHaveValue("");
    await vi.waitFor(() => expect(screen.getByRole("button", { name: "Iniciar sesión" })).toBeEnabled());
    expect(screen.queryByText("Sesión autenticada.")).not.toBeInTheDocument();
  });

  it("shows a generic error for invalid credentials without reflecting provider details", async () => {
    const authClient: AuthClient = {
      onSessionChange: () => () => {},
      loadSession: async () => ({ kind: "anonymous" }),
      signIn: vi.fn().mockRejectedValue(new Error("private account <INVALID_PASSWORD_PLACEHOLDER>")),
      signOut: vi.fn(),
    };
    render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);
    await screen.findByRole("button", { name: "Iniciar sesión" });
    fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "user@example.com" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "<INVALID_PASSWORD_PLACEHOLDER>" } });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar sesión" }));
    expect(await screen.findByText("No fue posible iniciar sesión. Revisa tus credenciales e inténtalo de nuevo.")).toBeInTheDocument();
    expect(screen.getByLabelText("Contraseña")).toHaveValue("");
    expect(document.body.innerHTML.includes("INVALID_PASSWORD_PLACEHOLDER")).toBe(false);
    expect(screen.queryByText(/private account/)).not.toBeInTheDocument();
  });

  it("shows the server-assigned role and allows logout", async () => {
    const authClient: AuthClient = {
      onSessionChange: () => () => {},
      loadSession: async () => ({
        kind: "authenticated",
        organizationId: "00000000-0000-0000-0000-000000000001",
        role: "analista",
      }),
      signIn: vi.fn(),
      signOut: vi.fn().mockResolvedValue(undefined),
    };
    render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);

    expect(await screen.findByText("Rol asignado por el servidor: analista.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    expect(authClient.signOut).toHaveBeenCalledOnce();
    expect(await screen.findByRole("button", { name: "Iniciar sesión" })).toBeInTheDocument();
  });

  it("identifies an unavailable Supabase configuration without exposing a secret", async () => {
    const authClient: AuthClient = {
      onSessionChange: () => () => {},
      loadSession: async () => ({ kind: "configuration-required" }),
      signIn: vi.fn(),
      signOut: vi.fn(),
    };
    render(<App authClient={authClient} loadHealth={async () => ({ status: "ok", version: "test", environment: "test" })} />);

    expect(await screen.findByText(/pendiente de configuración por EAG/)).toBeInTheDocument();
    expect(screen.queryByText(/service_role/i)).not.toBeInTheDocument();
  });
});
