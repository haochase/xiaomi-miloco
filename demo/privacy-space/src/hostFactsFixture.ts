import type { HostPrivacyFacts } from "./hostAdapter";
import { projectHostFacts } from "./hostAdapter";

type FixtureRecord = Record<string, unknown>;

function isForbiddenKey(key: string): boolean {
  const normalized = key.replace(/[^a-z]/gi, "").toLowerCase();
  return normalized === "owner" || normalized === "deviceid" || normalized === "absolutepath" ||
    normalized === "media" || normalized === "rawframe" || normalized === "token" || normalized === "apikey";
}

function isRecord(value: unknown): value is FixtureRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasForbiddenKey(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(hasForbiddenKey);
  if (!isRecord(value)) return false;
  return Object.entries(value).some(([key, child]) => isForbiddenKey(key) || hasForbiddenKey(child));
}

function validMetadata(value: unknown): value is HostPrivacyFacts["metadata"] {
  if (!isRecord(value) || typeof value.observedAt !== "string" || typeof value.expiresAt !== "string" || value.source !== "host") return false;
  const observedAt = Date.parse(value.observedAt);
  const expiresAt = Date.parse(value.expiresAt);
  return Number.isFinite(observedAt) && Number.isFinite(expiresAt) && expiresAt >= observedAt && expiresAt - observedAt <= 60 * 60 * 1000;
}

export function parseHostPrivacyFactsFixture(value: unknown): HostPrivacyFacts {
  if (!isRecord(value) || value.schemaVersion !== 1 || hasForbiddenKey(value)) {
    throw new Error("invalid host facts fixture");
  }
  const candidate: HostPrivacyFacts = {};
  if (value.metadata !== undefined) {
    if (!validMetadata(value.metadata)) throw new Error("invalid host facts fixture");
    candidate.metadata = value.metadata;
  }
  if (value.rooms !== undefined) candidate.rooms = value.rooms as HostPrivacyFacts["rooms"];
  if (value.anonymousPeopleCount !== undefined) {
    candidate.anonymousPeopleCount = value.anonymousPeopleCount as number;
  }
  if (value.outfit !== undefined) candidate.outfit = value.outfit as HostPrivacyFacts["outfit"];
  try {
    projectHostFacts(candidate);
  } catch {
    throw new Error("invalid host facts fixture");
  }
  return candidate;
}
