import { createClient } from "@supabase/supabase-js";
import { afterEach, expect, it, vi } from "vitest";
import { browserAuthClientOptions } from "./auth";

afterEach(() => { localStorage.clear(); window.history.replaceState(null, "", "/"); });

it.each(["invite", "magiclink"])("SDK consumes a synthetic %s hash before getSession resolves (offline HTTP stub)", async (type) => {
  // Real SDK, synthetic callback and stubbed Auth HTTP; not a Supabase integration.
  window.history.replaceState(null, "", `/#access_token=synthetic-access&refresh_token=synthetic-refresh&expires_in=3600&token_type=bearer&type=${type}`);
  let respond!: (value: Response) => void;
  const request = vi.fn(() => new Promise<Response>((resolve) => { respond = resolve; }));
  const client = createClient("https://example.supabase.co", "synthetic-public-key", {
    ...browserAuthClientOptions,
    global: { fetch: request },
  });
  try {
    let settled = false;
    const pending = client.auth.getSession().then((result) => { settled = true; return result; });
    await vi.waitFor(() => expect(request).toHaveBeenCalledOnce());
    expect(settled).toBe(false);
    respond(new Response(JSON.stringify({ id: "00000000-0000-0000-0000-000000000001", aud: "authenticated" })));
    const { data, error } = await pending;
    expect(error).toBeNull();
    expect(data.session).not.toBeNull();
    expect(window.location.hash).toBe("");
    expect(localStorage.length).toBeGreaterThan(0);
  } finally {
    await client.auth.dispose();
  }
});
