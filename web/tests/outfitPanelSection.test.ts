import { describe, expect, it } from "vitest";
import { initialOutfitPanelSection } from "@/components/outfit/outfitPanelSection";

describe("Outfit panel section selection", () => {
  it("opens wardrobe for the normal agent entry and moments for a moment deep link", () => {
    expect(initialOutfitPanelSection()).toBe("wardrobe");
    expect(initialOutfitPanelSection("moment-1")).toBe("moments");
  });
});
