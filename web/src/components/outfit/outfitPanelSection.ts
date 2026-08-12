export type OutfitPanelSection = "today" | "wardrobe" | "moments";

export function initialOutfitPanelSection(momentId?: string): OutfitPanelSection {
  return momentId ? "moments" : "wardrobe";
}
