import type { DemoState } from "./demoSchema";
import { projectOutfitRecommendation } from "./outfitProjection";

export const syntheticWardrobe: Array<{
  itemId: string;
  name: string;
  status: "confirmed";
  availability: "available";
}> = [
  { itemId: "top-1", name: "浅色针织上衣", status: "confirmed", availability: "available" },
  { itemId: "bottom-1", name: "深色长裤", status: "confirmed", availability: "available" },
  { itemId: "outerwear-1", name: "轻薄外套", status: "confirmed", availability: "available" },
  { itemId: "shoes-1", name: "运动鞋", status: "confirmed", availability: "available" },
];

export const syntheticRecommendation: {
  context: { activity: string };
  status: "ready";
  optionItemIds: string[][];
} = {
  context: { activity: "通勤" },
  status: "ready",
  optionItemIds: [["top-1", "bottom-1"], ["outerwear-1", "shoes-1"]],
};

export const demoState: DemoState = {
  rooms: [
    { id: "room-living", name: "客厅", width: 7, depth: 5, evidence: "confirmed" },
    { id: "room-bedroom", name: "卧室", width: 4, depth: 3, evidence: "inferred" },
  ],
  devices: [
    { type: "camera", label: "室内感知", online: true },
    { type: "lamp", label: "落地灯", online: true },
    { type: "speaker", label: "语音播报", online: false },
  ],
  peopleCount: 1,
  outfit: projectOutfitRecommendation(syntheticRecommendation, syntheticWardrobe),
  privacy: {
    status: "idle",
    temporaryFrameCleared: false,
    frameCount: 0,
    errorCode: null,
  },
};
