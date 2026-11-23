import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({
  getSession: vi.fn(), onAuthStateChange: vi.fn(), signInWithPassword: vi.fn(), signOut: vi.fn(),
}));
vi.mock("@supabase/supabase-js", () => ({ createClient: () => ({ auth: sdk }) }));

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("VITE_SUPABASE_URL", "https://example.supabase.co");
  vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", "synthetic-public-key");
  vi.stubEnv("VITE_API_BASE_URL", "");
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.resetAllMocks(); });

async function client() { return (await import("./auth")).createBrowserAuthClient(); }

describe("browser auth adapter (offline, mocked provider)", () => {
  it("does not call the API without a provider session", async () => {
    sdk.getSession.mockResolvedValue({ data: { session: null }, error: null });
    expect(await (await client()).loadSession()).toEqual({ kind: "anonymous" });
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([401, 403, 503])("reports only safe status %s and never trusts provider session as permissions", async (status) => {
    sdk.getSession.mockResolvedValue({ data: { session: { access_token: "synthetic-access" } }, error: null });
    vi.mocked(fetch).mockResolvedValue(new Response("private provider body", { status }));
    const auth = await client();
    await expect(auth.loadSession()).rejects.toMatchObject({ status });
  });

  it("waits for the SDK before checking server-assigned permissions", async () => {
    let complete!: (value: unknown) => void;
    sdk.getSession.mockReturnValue(new Promise((resolve) => { complete = resolve; }));
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ organization_id: "synthetic", role: "analista" })));
    const pending = (await client()).loadSession();
    expect(fetch).not.toHaveBeenCalled();
    complete({ data: { session: { access_token: "synthetic-access" } }, error: null });
    await expect(pending).resolves.toEqual({ kind: "authenticated", organizationId: "synthetic", role: "analista" });
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/auth/session");
  });

  it("subscribes synchronously without calling Auth inside the event and unsubscribes", async () => {
    let emit!: () => void;
    const unsubscribe = vi.fn();
    sdk.onAuthStateChange.mockImplementation((listener) => {
      emit = listener;
      return { data: { subscription: { unsubscribe } } };
    });
    const changed = vi.fn();
    const stop = (await client()).onSessionChange(changed);
    expect(emit()).toBeUndefined();
    expect(changed).toHaveBeenCalledOnce();
    expect(sdk.getSession).not.toHaveBeenCalled();
    stop();
    expect(unsubscribe).toHaveBeenCalledOnce();
  });

  it("uses an explicit API origin when configured", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.invalid/");
    sdk.getSession.mockResolvedValue({ data: { session: { access_token: "synthetic-access" } }, error: null });
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ organization_id: "synthetic", role: "analista" })));
    await (await client()).loadSession();
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("https://api.example.invalid/auth/session");
  });

  it("sends credentials only to Supabase and does not call our API during sign-in", async () => {
    sdk.signInWithPassword.mockResolvedValue({ error: null });
    await (await client()).signIn("user@example.com", "<INVALID_PASSWORD_PLACEHOLDER>");
    expect(sdk.signInWithPassword).toHaveBeenCalledOnce();
    const [credentials] = sdk.signInWithPassword.mock.calls[0];
    expect(credentials.email === "user@example.com").toBe(true);
    expect(credentials.password === "<INVALID_PASSWORD_PLACEHOLDER>").toBe(true);
    expect(Object.keys(credentials).sort()).toEqual(["email", "password"]);
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each(["returned", "thrown"])("sanitizes %s provider errors without retaining credentials", async (mode) => {
    const providerError = new Error("private account detail <INVALID_PASSWORD_PLACEHOLDER>");
    if (mode === "returned") sdk.signInWithPassword.mockResolvedValue({ error: providerError });
    else sdk.signInWithPassword.mockRejectedValue(providerError);
    const error = await (await client()).signIn("user@example.com", "<INVALID_PASSWORD_PLACEHOLDER>")
      .catch((failure: unknown) => failure);
    const { signInErrorMessage } = await import("./auth");
    expect(error instanceof Error && error.message === signInErrorMessage).toBe(true);
    expect(error instanceof Error && "cause" in error).toBe(false);
    expect(String(error).includes("<INVALID_PASSWORD_PLACEHOLDER>")).toBe(false);
    expect(fetch).not.toHaveBeenCalled();
  });
});
