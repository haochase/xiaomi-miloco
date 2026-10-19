import { describe, expect, it } from "vitest";
import { freshnessLabel } from "../src/freshness";

describe("freshnessLabel", () => {
  it("returns fresh for an unexpired host fact", () => {
    expect(freshnessLabel({ observedAt: "2026-10-19T10:00:00Z", expiresAt: "2026-10-19T10:10:00Z", source: "host" }, new Date("2026-10-19T10:05:00Z"))).toBe("fresh");
  });

  it("returns unknown when metadata is absent or expired", () => {
    expect(freshnessLabel(undefined, new Date("2026-10-19T10:05:00Z"))).toBe("unknown");
    expect(freshnessLabel({ observedAt: "2026-10-19T10:00:00Z", expiresAt: "2026-10-19T10:10:00Z", source: "host" }, new Date("2026-10-19T10:10:01Z"))).toBe("unknown");
  });
});
