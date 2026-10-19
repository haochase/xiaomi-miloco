import { describe, expect, it } from "vitest";
import { parseHostPrivacyFactsFixture } from "../src/hostFactsFixture";

describe("parseHostPrivacyFactsFixture", () => {
  it("accepts a versioned fixture and drops ordinary extension fields", () => {
    const facts = parseHostPrivacyFactsFixture({
      schemaVersion: 1,
      metadata: { observedAt: "2026-10-19T10:00:00Z", expiresAt: "2026-10-19T10:10:00Z", source: "host" },
      rooms: [{ id: "living", name: "客厅", width: 7, depth: 5, confirmed: true }],
      anonymousPeopleCount: 0,
      outfit: { scene: "通勤", candidates: ["浅色上衣"], ready: true },
      futureExtension: "drop-me",
    });
    expect(facts).toEqual({
      metadata: { observedAt: "2026-10-19T10:00:00Z", expiresAt: "2026-10-19T10:10:00Z", source: "host" },
      rooms: [{ id: "living", name: "客厅", width: 7, depth: 5, confirmed: true }],
      anonymousPeopleCount: 0,
      outfit: { scene: "通勤", candidates: ["浅色上衣"], ready: true },
    });
  });

  it("preserves bounded freshness metadata without device or location identifiers", () => {
    const facts = parseHostPrivacyFactsFixture({
      schemaVersion: 1,
      metadata: { observedAt: "2026-10-19T10:00:00Z", expiresAt: "2026-10-19T10:10:00Z", source: "host" },
    });
    expect(facts.metadata).toEqual({
      observedAt: "2026-10-19T10:00:00Z",
      expiresAt: "2026-10-19T10:10:00Z",
      source: "host",
    });
  });

  it("rejects invalid or expired freshness metadata", () => {
    expect(() => parseHostPrivacyFactsFixture({ schemaVersion: 1, metadata: { observedAt: "bad", expiresAt: "2026-10-19T10:10:00Z", source: "host" } })).toThrow("invalid host facts fixture");
    expect(() => parseHostPrivacyFactsFixture({ schemaVersion: 1, metadata: { observedAt: "2026-10-19T10:10:00Z", expiresAt: "2026-10-19T09:59:00Z", source: "host" } })).toThrow("invalid host facts fixture");
    expect(() => parseHostPrivacyFactsFixture({ schemaVersion: 1, metadata: { observedAt: "2026-10-19T10:00:00Z", expiresAt: "2026-10-19T10:10:00Z", source: "camera-1" } })).toThrow("invalid host facts fixture");
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

  it("rejects malformed facts instead of deferring validation to the view adapter", () => {
    expect(() => parseHostPrivacyFactsFixture({ schemaVersion: 1, rooms: [{ id: "living" }] })).toThrow("invalid host facts fixture");
    expect(() => parseHostPrivacyFactsFixture({ schemaVersion: 1, anonymousPeopleCount: "0" })).toThrow("invalid host facts fixture");
    expect(() => parseHostPrivacyFactsFixture({ schemaVersion: 1, outfit: { scene: "通勤", candidates: "浅色上衣", ready: true } })).toThrow("invalid host facts fixture");
  });
});
