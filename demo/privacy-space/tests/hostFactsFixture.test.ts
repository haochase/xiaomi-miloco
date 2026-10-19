import { describe, expect, it } from "vitest";
import { parseHostPrivacyFactsFixture } from "../src/hostFactsFixture";

describe("parseHostPrivacyFactsFixture", () => {
  it("accepts a versioned fixture and drops ordinary extension fields", () => {
    const facts = parseHostPrivacyFactsFixture({
      schemaVersion: 1,
      rooms: [{ id: "living", name: "客厅", width: 7, depth: 5, confirmed: true }],
      anonymousPeopleCount: 0,
      outfit: { scene: "通勤", candidates: ["浅色上衣"], ready: true },
      futureExtension: "drop-me",
    });
    expect(facts).toEqual({
      rooms: [{ id: "living", name: "客厅", width: 7, depth: 5, confirmed: true }],
      anonymousPeopleCount: 0,
      outfit: { scene: "通勤", candidates: ["浅色上衣"], ready: true },
    });
  });

  it("rejects missing or unsupported schema versions", () => {
    expect(() => parseHostPrivacyFactsFixture({ rooms: [] })).toThrow("invalid host facts fixture");
    expect(() => parseHostPrivacyFactsFixture({ schemaVersion: 2, rooms: [] })).toThrow("invalid host facts fixture");
  });

  it("rejects raw media, owner selectors, and device identifiers", () => {
    expect(() => parseHostPrivacyFactsFixture({ schemaVersion: 1, owner: "chase" })).toThrow("invalid host facts fixture");
    expect(() => parseHostPrivacyFactsFixture({ schemaVersion: 1, deviceId: "camera-1" })).toThrow("invalid host facts fixture");
    expect(() => parseHostPrivacyFactsFixture({ schemaVersion: 1, media: { bytes: "..." } })).toThrow("invalid host facts fixture");
  });
});
