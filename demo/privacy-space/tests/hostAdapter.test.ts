import { describe, expect, it } from "vitest";
import { projectHostFacts } from "../src/hostAdapter";
import { serializeDemoState } from "../src/demoSchema";

describe("projectHostFacts", () => {
  it("keeps missing host facts unknown without inventing room or person state", () => {
    const state = projectHostFacts({});
    expect(state.rooms).toEqual([]);
    expect(state.devices).toEqual([]);
    expect(state.peopleCount).toBeNull();
    expect(state.outfit.status).toBe("unavailable");
  });

  it("accepts an explicitly empty room list", () => {
    expect(projectHostFacts({ rooms: [] }).rooms).toEqual([]);
  });

  it("keeps an explicit zero distinct from an unknown people count", () => {
    expect(projectHostFacts({ anonymousPeopleCount: 0 }).peopleCount).toBe(0);
  });

  it("projects a named room without inventing geometry or confirmation", () => {
    const state = projectHostFacts({ rooms: [{ id: "living", name: "客厅" }] });
    expect(state.rooms).toEqual([{ id: "living", name: "客厅", width: null, depth: null, evidence: "unknown" }]);
  });

  it("requires dimensions before treating a room as confirmed", () => {
    expect(() => projectHostFacts({ rooms: [{ id: "living", name: "客厅", confirmed: true }] })).toThrow("invalid host facts");
  });

  it("rejects partial geometry", () => {
    expect(() => projectHostFacts({ rooms: [{ id: "living", name: "客厅", width: 7 }] })).toThrow("invalid host facts");
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

  it("rejects invalid counts and room geometry", () => {
    expect(() => projectHostFacts({ anonymousPeopleCount: -1 })).toThrow("invalid host facts");
    expect(() => projectHostFacts({ rooms: [{ id: "living", name: "客厅", width: -1, depth: 5, confirmed: true }] })).toThrow("invalid host facts");
  });

  it("rejects display values that look like paths or credentials", () => {
    expect(() => projectHostFacts({ rooms: [{ id: "living", name: "C:\\private\\home", width: 7, depth: 5, confirmed: true }] })).toThrow("invalid host facts");
    expect(() => projectHostFacts({ outfit: { scene: "通勤", candidates: ["token=private"], ready: true } })).toThrow("invalid host facts");
  });
});
