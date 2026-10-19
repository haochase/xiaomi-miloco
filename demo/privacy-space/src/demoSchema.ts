export type EvidenceLevel = "confirmed" | "inferred" | "unknown";

export type DemoRoom = {
  id: string;
  name: string;
  width: number | null;
  depth: number | null;
  evidence: EvidenceLevel;
};

export type DemoDevice = {
  type: "camera" | "lamp" | "speaker";
  label: string;
  online: boolean;
};

export type DemoState = {
  rooms: DemoRoom[];
  devices: DemoDevice[];
  peopleCount: number | null;
  outfit: {
    scene: string;
    status: "ready" | "insufficient" | "unavailable";
    candidates: string[];
  };
  privacy: {
    status: "idle" | "processed" | "failed";
    temporaryFrameCleared: boolean;
    frameCount: number;
    errorCode: string | null;
  };
};

export function serializeDemoState(state: DemoState): string {
  return JSON.stringify({
    rooms: state.rooms.map(({ id, name, width, depth, evidence }) => ({ id, name, width, depth, evidence })),
    devices: state.devices.map(({ type, label, online }) => ({ type, label, online })),
    peopleCount: state.peopleCount,
    outfit: {
      scene: state.outfit.scene,
      status: state.outfit.status,
      candidates: [...state.outfit.candidates],
    },
    privacy: {
      status: state.privacy.status,
      temporaryFrameCleared: state.privacy.temporaryFrameCleared,
      frameCount: state.privacy.frameCount,
      errorCode: state.privacy.errorCode,
    },
  });
}
