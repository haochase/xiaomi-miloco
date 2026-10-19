import type { DemoState } from "./demoSchema";

type OutfitWardrobeItem = {
  itemId: string;
  name: string;
  status: "confirmed";
  availability: "available";
};

type OutfitRecommendationSnapshot = {
  context: { activity: string | null };
  status: "ready" | "insufficient_inventory";
  optionItemIds: string[][];
};

type DemoOutfit = DemoState["outfit"];

const unavailable: DemoOutfit = { scene: "", status: "unavailable", candidates: [] };

function safeName(value: string): boolean {
  return value.length > 0 && value.length <= 80 && !/[\\/]|[A-Za-z]:|(?:token|secret|password|key)\s*=/i.test(value);
}

export function projectOutfitRecommendation(
  snapshot: OutfitRecommendationSnapshot,
  availableItems: OutfitWardrobeItem[],
): DemoOutfit {
  if (
    snapshot.status !== "ready" ||
    snapshot.optionItemIds.length < 2 || snapshot.optionItemIds.length > 3 ||
    !snapshot.context.activity || !safeName(snapshot.context.activity)
  ) return unavailable;

  const items = new Map<string, string>();
  for (const item of availableItems) {
    if (item.status === "confirmed" && item.availability === "available" && safeName(item.name)) {
      items.set(item.itemId, item.name);
    }
  }

  const candidates: string[] = [];
  for (const option of snapshot.optionItemIds) {
    if (option.length < 2) return unavailable;
    const names = option.map((itemId) => items.get(itemId));
    if (names.some((name) => name === undefined)) return unavailable;
    candidates.push((names as string[]).join(" + "));
  }
  return { scene: snapshot.context.activity, status: "ready", candidates };
}
