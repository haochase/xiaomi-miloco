import type { DemoState } from "./demoSchema";

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
  outfit: {
    scene: "通勤",
    status: "ready",
    candidates: ["浅色针织上衣 + 深色长裤", "轻薄外套 + 运动鞋"],
  },
  privacy: {
    status: "processed",
    temporaryFrameCleared: true,
    frameCount: 1,
    errorCode: null,
  },
};
