import type { HostPrivacyFacts } from "./hostAdapter";

export type Freshness = "fresh" | "unknown";

export function freshnessLabel(metadata: HostPrivacyFacts["metadata"], now: Date): Freshness {
  if (!metadata) return "unknown";
  const expiresAt = Date.parse(metadata.expiresAt);
  return Number.isFinite(expiresAt) && expiresAt >= now.getTime() ? "fresh" : "unknown";
}
