import { describe, expect, it } from "vitest";
import { refreshDemoScenario } from "../src/demoRefresh";
import { finishRefresh, startRefresh } from "../src/refreshState";

describe("refreshDemoScenario", () => {
  it("reloads the selected local fixture without changing the scenario", () => {
    const state = refreshDemoScenario("fixture");
    expect(state.factsFreshness).toBe("fresh");
    expect(state.outfit.candidates).toEqual(["浅色上衣"]);
  });

  it("falls back to the synthetic default for an unknown scenario", () => {
    expect(refreshDemoScenario("unexpected").peopleCount).toBe(1);
  });

  it("keeps the local refresh state explicit", () => {
    expect(finishRefresh(startRefresh({ status: "idle", errorCode: null }), true).status).toBe("succeeded");
  });

  it("uses a fixed failure state when the local fixture loader fails", () => {
    expect(finishRefresh(startRefresh({ status: "idle", errorCode: null }), false)).toEqual({
      status: "failed",
      errorCode: "fixture_unavailable",
    });
  });
});
