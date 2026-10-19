import { describe, expect, it } from "vitest";
import { parsePrivacyFactsSnapshot } from "../src/privacySnapshot";

describe("parsePrivacyFactsSnapshot", () => {
  it("accepts bounded low-sensitivity snapshot fields", () => {
    expect(parsePrivacyFactsSnapshot({
      snapshotId: "opaque-1",
      freshness: "fresh",
      rooms: [{ id: "living", displayName: "客厅", evidence: "unknown" }],
      anonymousPeopleCount: null,
      outfitSummary: ["浅色上衣"],
    })).toEqual({
      snapshotId: "opaque-1",
      freshness: "fresh",
      rooms: [{ id: "living", displayName: "客厅", evidence: "unknown" }],
      anonymousPeopleCount: null,
      outfitSummary: ["浅色上衣"],
    });
  });

  it("rejects owner, device, path, media, and raw answer fields", () => {
    expect(() => parsePrivacyFactsSnapshot({ snapshotId: "owner=secret" })).toThrow("invalid privacy facts snapshot");
    expect(() => parsePrivacyFactsSnapshot({ snapshotId: "opaque-1", deviceId: "camera-1" })).toThrow("invalid privacy facts snapshot");
    expect(() => parsePrivacyFactsSnapshot({ snapshotId: "opaque-1", rawMedia: "..." })).toThrow("invalid privacy facts snapshot");
  });

  it("rejects invalid freshness and candidate counts", () => {
    expect(() => parsePrivacyFactsSnapshot({ snapshotId: "opaque-1", freshness: "stale" })).toThrow("invalid privacy facts snapshot");
    expect(() => parsePrivacyFactsSnapshot({ snapshotId: "opaque-1", freshness: "fresh", outfitSummary: ["a", "b", "c", "d"] })).toThrow("invalid privacy facts snapshot");
  });
});
