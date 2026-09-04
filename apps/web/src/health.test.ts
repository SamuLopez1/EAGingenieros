import { describe, expect, it } from "vitest";

import { healthUrlFor } from "./health";

describe("healthUrlFor", () => {
  it("uses the Vite proxy when the configured base URL is absent or blank", () => {
    expect(healthUrlFor(undefined)).toBe("/api/health");
    expect(healthUrlFor("")).toBe("/api/health");
    expect(healthUrlFor("   ")).toBe("/api/health");
  });

  it("normalizes a configured base URL before adding the health path", () => {
    expect(healthUrlFor(" https://api.example.test/ ")).toBe(
      "https://api.example.test/health",
    );
  });
});
