import { afterEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({ getAccessToken: vi.fn() }));
vi.mock("../auth", () => ({ browserAuthClient: auth }));
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetModules(); vi.clearAllMocks(); });

describe("catálogo con sesión compartida", () => {
  it("envía el token actual sin duplicar el prefijo /api", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "/api");
    auth.getAccessToken.mockResolvedValue("synthetic-session");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] })));
    vi.stubGlobal("fetch", fetchMock);
    const { fetchOpportunities } = await import("./client");
    await fetchOpportunities({ limit: 25 });
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/opportunities?limit=25", expect.objectContaining({
      headers: expect.objectContaining({ Authorization: "Bearer synthetic-session" }),
    }));
  });

  it("falla cerrada si no hay sesión, sin consultar negocio", async () => {
    auth.getAccessToken.mockResolvedValue(null);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { fetchOpportunities } = await import("./client");
    await expect(fetchOpportunities()).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
