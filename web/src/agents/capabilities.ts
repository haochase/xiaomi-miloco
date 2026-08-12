import type { AgentPanelRegistry } from "./registry";
import type { AgentPanelContribution } from "./types";

export interface AgentCapabilitySnapshot {
  id: string;
  enabled: boolean;
  api_version: string;
}

export function enabledAgentCapabilityIds(
  capabilities: readonly AgentCapabilitySnapshot[],
): Set<string> {
  return new Set(
    capabilities
      .filter((capability) => capability.enabled)
      .map((capability) => capability.id),
  );
}

export function listVisibleAgentPanelContributions(
  registry: AgentPanelRegistry,
  capabilities: readonly AgentCapabilitySnapshot[],
): AgentPanelContribution[] {
  const enabledIds = enabledAgentCapabilityIds(capabilities);
  return registry
    .list()
    .filter((contribution) => enabledIds.has(contribution.capabilityId));
}
