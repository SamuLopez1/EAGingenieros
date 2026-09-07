import { describe, expect, it } from "vitest";

import { browserAuthClientOptions } from "./auth";

describe("browserAuthClientOptions", () => {
  it("consumes and retains the invite or magic-link callback in the browser", () => {
    expect(browserAuthClientOptions.auth).toEqual({
      autoRefreshToken: true,
      persistSession: true,
      detectSessionInUrl: true,
    });
  });
});
