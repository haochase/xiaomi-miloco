import { describe, expect, it } from "vitest";
import { projectHostFacts } from "../src/hostAdapter";
import { scenePresentation } from "../src/scenePresentation";

describe("scenePresentation", () => {
  it("uses a list when room geometry or people count is unknown", () => {
    const state = projectHostFacts({ rooms: [{ id: "living", name: "客厅" }] });
    expect(scenePresentation(state.rooms, state.peopleCount)).toEqual({
      mode: "list",
      peopleLabel: "活动人数未知",
    });
  });

  it("preserves the explicit synthetic floorplan and zero count", () => {
    const state = projectHostFacts({
      rooms: [{ id: "living", name: "客厅", width: 7, depth: 5, confirmed: true }],
      anonymousPeopleCount: 0,
    });
    expect(scenePresentation(state.rooms, state.peopleCount)).toEqual({
      mode: "floorplan",
      peopleLabel: "0 位匿名活动者",
    });
  });

  it("does not draw a floorplan from unconfirmed dimensions", () => {
    const state = projectHostFacts({
      rooms: [{ id: "living", name: "客厅", width: 7, depth: 5, confirmed: false }],
      anonymousPeopleCount: 0,
    });
    expect(scenePresentation(state.rooms, state.peopleCount).mode).toBe("list");
  });

  it("does not draw a floorplan when the people count is unknown", () => {
    const state = projectHostFacts({
      rooms: [{ id: "living", name: "客厅", width: 7, depth: 5, confirmed: true }],
    });
    expect(scenePresentation(state.rooms, state.peopleCount).mode).toBe("list");
  });
});
