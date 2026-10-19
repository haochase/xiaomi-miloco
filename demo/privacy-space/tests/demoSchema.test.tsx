import { describe, expect, it } from "vitest";
import { demoState, syntheticRecommendation, syntheticWardrobe } from "../src/demoData";
import { serializeDemoState } from "../src/demoSchema";
import { projectOutfitRecommendation } from "../src/outfitProjection";

describe("privacy space demo state", () => {
  it("contains only structured, low-sensitivity fields", () => {
    const serialized = serializeDemoState(demoState);

    expect(demoState.rooms.length).toBeGreaterThan(0);
    expect(demoState.devices.some((device) => device.type === "camera")).toBe(true);
    expect(demoState.outfit.candidates.length).toBe(2);
    expect(demoState.outfit.candidates).toEqual([
      "浅色针织上衣 + 深色长裤",
      "轻薄外套 + 运动鞋",
    ]);
    expect(demoState.outfit).toEqual(
      projectOutfitRecommendation(syntheticRecommendation, syntheticWardrobe),
    );
    expect(serialized).not.toMatch(/owner|device_id|token|path|secret|raw|provider/i);
    expect(demoState.privacy.status).toBe("idle");
    expect(demoState.factsFreshness).toBe("unknown");
    expect(demoState.privacy.temporaryFrameCleared).toBe(false);
  });

});
