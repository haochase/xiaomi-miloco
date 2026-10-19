import { describe, expect, it } from "vitest";
import { projectHostFacts } from "../src/hostAdapter";
import { serializeDemoState } from "../src/demoSchema";

describe("projectHostFacts", () => {
  it("keeps missing host facts unknown without inventing room or person state", () => {
    const state = projectHostFacts({});
    expect(state.rooms).toEqual([]);
    expect(state.devices).toEqual([]);
    expect(state.peopleCount).toBe(0);
    expect(state.outfit.status).toBe("unavailable");
  });

  it("projects only bounded facts and drops extra sensitive fields", () => {
    const facts = {
      rooms: [{ id: "living", name: "客厅", width: 7, depth: 5, confirmed: true, owner_id: "private-owner" }],
      anonymousPeopleCount: 1,
      outfit: { scene: "通勤", candidates: ["浅色上衣 + 深色长裤"], ready: true, raw_provider_answer: "secret" },
      token: "private-token",
    };
    const serialized = serializeDemoState(projectHostFacts(facts));
    expect(serialized).toContain("客厅");
    expect(serialized).toContain("浅色上衣");
    expect(serialized).not.toMatch(/private-owner|private-token|raw_provider_answer|secret/);
  });
});
