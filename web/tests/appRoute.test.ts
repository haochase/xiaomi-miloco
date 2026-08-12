import { describe, expect, it } from "vitest";
import {
  formatAgentMomentRoute,
  formatAgentMomentsRoute,
  isAgentRoute,
  parseAppRoute,
  resolvePanelRoute,
} from "@/lib/appRoute";
import { toMomentQuery } from "@/components/outfit/OutfitMomentsView";

describe("application hash routes", () => {
  it("parses an Outfit moment deep link without changing the perf route", () => {
    expect(parseAppRoute("#/agents/outfit/moments/moment-1")).toEqual({
      tab: "agents",
      agentId: "outfit",
      view: "moment",
      momentId: "moment-1",
    });
    expect(parseAppRoute("#perf")).toEqual({ tab: "perf" });
  });

  it("marks only agent paths as lightweight agent-panel routes", () => {
    expect(isAgentRoute(parseAppRoute("#/agents/outfit"))).toBe(true);
    expect(isAgentRoute(parseAppRoute("#perf"))).toBe(false);
    expect(isAgentRoute(parseAppRoute("#not-an-agent"))).toBe(false);
  });

  it("defaults an isolated panel sidecar to the Outfit route only", () => {
    expect(
      resolvePanelRoute({ tab: "now" }, { outfitSidecar: true }),
    ).toEqual({ tab: "agents", agentId: "outfit" });
    expect(
      resolvePanelRoute({ tab: "now" }, { outfitSidecar: false }),
    ).toEqual({ tab: "now" });
  });

  it("round-trips encoded agent and moment identifiers", () => {
    const route = formatAgentMomentRoute("outfit guide", "moment/1");

    expect(route).toBe("#/agents/outfit%20guide/moments/moment%2F1");
    expect(parseAppRoute(route)).toEqual({
      tab: "agents",
      agentId: "outfit guide",
      view: "moment",
      momentId: "moment/1",
    });
  });

  it("parses the Outfit history route and creates its bounded time queries", () => {
    expect(formatAgentMomentsRoute("outfit")).toBe("#/agents/outfit/moments");
    expect(parseAppRoute("#/agents/outfit/moments")).toEqual({
      tab: "agents",
      agentId: "outfit",
      view: "moments",
    });
    expect(toMomentQuery("recent10", 1000)).toEqual({ limit: 10 });
    expect(toMomentQuery("recent30", 1000)).toEqual({ limit: 30 });
    expect(toMomentQuery("month", Date.UTC(2026, 7, 11))).toEqual({
      limit: 30,
      sinceMs: Date.UTC(2026, 6, 12),
    });
  });

  it("rejects malformed, empty, and oversized path segments", () => {
    expect(parseAppRoute("#/agents//moments/moment-1")).toEqual({ tab: "now" });
    expect(parseAppRoute("#/agents/%E0%A4%A")).toEqual({ tab: "now" });
    expect(parseAppRoute(`#/agents/${"a".repeat(129)}`)).toEqual({ tab: "now" });
  });
});
