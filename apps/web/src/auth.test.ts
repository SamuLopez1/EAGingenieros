import { describe, expect, it, vi } from "vitest";

const { createClient } = vi.hoisted(() => ({
  createClient: vi.fn(() => ({
    auth: {
      getSession: vi.fn(),
      signInWithOtp: vi.fn(),
      signOut: vi.fn(),
    },
  })),
}));

vi.mock("@supabase/supabase-js", () => ({ createClient }));

import { createBrowserAuthClient } from "./auth";

describe("createBrowserAuthClient", () => {
  it("consumes the invite or magic-link callback in the browser", () => {
    createBrowserAuthClient();

    expect(createClient).toHaveBeenLastCalledWith(
      expect.any(String),
      expect.any(String),
      expect.objectContaining({
        auth: expect.objectContaining({ detectSessionInUrl: true, persistSession: false }),
      }),
    );
  });
});
