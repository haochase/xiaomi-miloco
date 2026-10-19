import { describe, expect, it } from "vitest";
import { projectOutfitRecommendation } from "../src/outfitProjection";
import type { OutfitRecommendationSnapshot, OutfitWardrobeItem } from "../../../web/src/api/outfit";

const inventory: OutfitWardrobeItem[] = [
  { itemId: "top-1", name: "浅色针织上衣", category: "top", sourceTypes: ["manual"], status: "confirmed", availability: "available" },
  { itemId: "bottom-1", name: "深色长裤", category: "bottom", sourceTypes: ["manual"], status: "confirmed", availability: "available" },
];

const snapshot: OutfitRecommendationSnapshot = {
  snapshotId: "rec-synthetic",
  context: { occasion: null, activity: "通勤", dayKind: "workday" },
  status: "ready",
  optionItemIds: [["top-1", "bottom-1"], ["bottom-1", "top-1"]],
  rankingVersion: "v1",
  createdAtMs: 1,
};

describe("projectOutfitRecommendation", () => {
  it("maps candidate ids to confirmed available display names only", () => {
    const result = projectOutfitRecommendation(snapshot, inventory);
    expect(result).toEqual({
      scene: "通勤",
      status: "ready",
      candidates: ["浅色针织上衣 + 深色长裤", "深色长裤 + 浅色针织上衣"],
    });
    expect(JSON.stringify(result)).not.toMatch(/top-1|bottom-1|rec-synthetic|rankingVersion/);
  });

  it("fails closed when a candidate is absent from confirmed inventory", () => {
    const unknown = { ...snapshot, optionItemIds: [["top-1", "missing"], ["bottom-1", "top-1"]] };
    expect(projectOutfitRecommendation(unknown, inventory)).toEqual({ scene: "", status: "unavailable", candidates: [] });
  });

  it("fails closed when an inventory name contains a path or credential shape", () => {
    const unsafe = [{ ...inventory[0], name: "C:\\private\\photo.jpg" }, inventory[1]];
    expect(projectOutfitRecommendation(snapshot, unsafe)).toEqual({ scene: "", status: "unavailable", candidates: [] });
  });
});
