type SnapshotRecord = Record<string, unknown>;

export type PrivacyFactsSnapshot = {
  snapshotId: string;
  freshness: "fresh" | "unknown";
  rooms: Array<{ id: string; displayName: string; evidence: "confirmed" | "inferred" | "unknown" }>;
  anonymousPeopleCount: number | null;
  outfitSummary: string[];
};

function isRecord(value: unknown): value is SnapshotRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeText(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 80 && !/[\\/]|[A-Za-z]:|(?:token|secret|password|key|owner|device|media)s*=/i.test(value);
}

function hasForbiddenKey(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(hasForbiddenKey);
  if (!isRecord(value)) return false;
  return Object.entries(value).some(([key, child]) => /owner|device|path|media|raw|token|secret/i.test(key) || hasForbiddenKey(child));
}

export function parsePrivacyFactsSnapshot(value: unknown): PrivacyFactsSnapshot {
  if (!isRecord(value) || hasForbiddenKey(value) || !safeText(value.snapshotId) || value.snapshotId.includes("=")) throw new Error("invalid privacy facts snapshot");
  const freshness = value.freshness ?? "unknown";
  const rooms = value.rooms ?? [];
  const people = value.anonymousPeopleCount ?? null;
  const summary = value.outfitSummary ?? [];
  if (freshness !== "fresh" && freshness !== "unknown") throw new Error("invalid privacy facts snapshot");
  if (!Array.isArray(rooms) || rooms.length > 20 || !Array.isArray(summary) || summary.length > 3 || summary.some((item) => !safeText(item))) throw new Error("invalid privacy facts snapshot");
  if (people !== null && (typeof people !== "number" || !Number.isInteger(people) || people < 0 || people > 20)) throw new Error("invalid privacy facts snapshot");
  const normalizedRooms = rooms.map((room) => {
    if (!isRecord(room) || !safeText(room.id) || !safeText(room.displayName) || !["confirmed", "inferred", "unknown"].includes(String(room.evidence))) throw new Error("invalid privacy facts snapshot");
    return { id: room.id, displayName: room.displayName, evidence: room.evidence as PrivacyFactsSnapshot["rooms"][number]["evidence"] };
  });
  return { snapshotId: value.snapshotId, freshness, rooms: normalizedRooms, anonymousPeopleCount: people === null ? null : people as number, outfitSummary: [...summary] };
}
