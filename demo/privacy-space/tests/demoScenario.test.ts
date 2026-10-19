import { describe, expect, it } from "vitest";
import { selectDemoScenario } from "../src/demoScenario";

describe("selectDemoScenario", () => {
  it("shows a named room without claiming a floorplan or people count", () => {
    const state = selectDemoScenario("room-names");
    expect(state.rooms).toEqual([{ id: "living", name: "客厅", width: null, depth: null, evidence: "unknown" }]);
    expect(state.peopleCount).toBeNull();
    expect(state.outfit.status).toBe("unavailable");
  });

  it("keeps the synthetic default when the scenario is unknown", () => {
    expect(selectDemoScenario("unexpected").peopleCount).toBe(1);
  });
});
