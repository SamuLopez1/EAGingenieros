import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the initial loading state", () => {
    render(<App loadHealth={() => new Promise(() => undefined)} />);

    expect(screen.getByRole("status")).toHaveTextContent("Comprobando conexión con la API");
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

    expect(await screen.findByRole("alert")).toHaveTextContent("No fue posible comprobar la conexión");
  });
});
