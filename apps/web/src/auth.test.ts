import { describe, expect, it } from "vitest";

import { browserAuthClientOptions } from "./auth";

describe("browserAuthClientOptions", () => {
  it("consumes the invite or magic-link callback in the browser", () => {
    expect(browserAuthClientOptions.auth).toEqual({
      autoRefreshToken: false,
      persistSession: false,
      detectSessionInUrl: true,
    });
  });
});
