import type { DemoState } from "./demoSchema";

export type HostPrivacyFacts = {
  rooms?: Array<{ id: string; name: string; width: number; depth: number; confirmed: boolean }>;
  anonymousPeopleCount?: number;
  outfit?: { scene: string; candidates: string[]; ready: boolean };
};

const unknownState: DemoState = {
  rooms: [],
  devices: [],
  peopleCount: 0,
  outfit: { scene: "", status: "unavailable", candidates: [] },
  privacy: { status: "idle", temporaryFrameCleared: false, frameCount: 0, errorCode: null },
};

export function projectHostFacts(facts: HostPrivacyFacts): DemoState {
  return {
    ...unknownState,
    rooms: (facts.rooms ?? []).map((room) => ({
      id: room.id,
      name: room.name,
      width: room.width,
      depth: room.depth,
      evidence: room.confirmed ? "confirmed" : "unknown",
    })),
    peopleCount: facts.anonymousPeopleCount ?? 0,
    outfit: facts.outfit
      ? {
          scene: facts.outfit.scene,
          status: facts.outfit.ready ? "ready" : "unavailable",
          candidates: facts.outfit.ready ? [...facts.outfit.candidates] : [],
        }
      : unknownState.outfit,
  };
}
