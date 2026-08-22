import { describe, expect, it } from "vitest";
import { parseAppRoute, serializeAppRoute } from "@/lib/appRoute";

describe("app hash routes", () => {
  it("parses the generic agents list and encoded agent IDs", () => {
    expect(parseAppRoute("#/agents")).toEqual({ kind: "agents" });
    expect(parseAppRoute("#/agents/weekly%20review%2Fteam")).toEqual({
      kind: "agents",
      agentId: "weekly review/team",
    });
  });

  it("serializes generic agents routes with encoded IDs", () => {
    expect(serializeAppRoute({ kind: "agents" })).toBe("#/agents");
    expect(
      serializeAppRoute({ kind: "agents", agentId: "weekly review/team" }),
    ).toBe("#/agents/weekly%20review%2Fteam");
  });

  it("preserves the existing perf hash route", () => {
    expect(parseAppRoute("#perf")).toEqual({ kind: "perf" });
    expect(serializeAppRoute({ kind: "perf" })).toBe("#perf");
  });

  it.each([
    "",
    "#",
    "#/agents/",
    "#/agents/%E0%A4%A",
    "#/agents/known/extra",
    "#/agents/known?view=compact",
    "#/agent",
    "#perf/extra",
  ])("falls back to the main page for unknown or malformed hash %s", (hash) => {
    expect(parseAppRoute(hash)).toEqual({ kind: "main" });
  });

  it("serializes the main page without a hash", () => {
    expect(serializeAppRoute({ kind: "main" })).toBe("");
  });
});
