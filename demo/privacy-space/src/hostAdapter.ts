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

function safeDisplayText(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= 80 &&
    !/[\\/]|[A-Za-z]:|(?:token|secret|password|key)\s*=/i.test(value)
  );
}

function validFacts(facts: HostPrivacyFacts): boolean {
  const count = facts.anonymousPeopleCount;
  if (count !== undefined && (!Number.isInteger(count) || count < 0 || count > 20)) {
    return false;
  }
  if (facts.rooms) {
    if (!Array.isArray(facts.rooms) || facts.rooms.length > 20) return false;
    for (const room of facts.rooms) {
      if (
        !safeDisplayText(room.id) ||
        !safeDisplayText(room.name) ||
        !Number.isFinite(room.width) ||
        !Number.isFinite(room.depth) ||
        room.width <= 0 || room.depth <= 0 ||
        room.width > 100 || room.depth > 100 ||
        typeof room.confirmed !== "boolean"
      ) return false;
    }
  }
  if (facts.outfit) {
    if (
      !safeDisplayText(facts.outfit.scene) ||
      typeof facts.outfit.ready !== "boolean" ||
      !Array.isArray(facts.outfit.candidates) ||
      facts.outfit.candidates.length > 3 ||
      facts.outfit.candidates.some((candidate) => !safeDisplayText(candidate))
    ) return false;
  }
  return true;
}

export function projectHostFacts(facts: HostPrivacyFacts): DemoState {
  if (!validFacts(facts)) throw new Error("invalid host facts");
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
