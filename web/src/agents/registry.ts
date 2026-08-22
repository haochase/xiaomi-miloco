import type { AgentPanelContribution } from "./types";

export interface AgentRegistry {
  readonly all: readonly AgentPanelContribution[];
  find(id: string): AgentPanelContribution | undefined;
  visibleFor(
    successfulCapabilityIds: ReadonlySet<string>,
  ): readonly AgentPanelContribution[];
}

function requireText(value: string, field: string): void {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`Agent contribution ${field} must not be blank`);
  }
}

function compareAgentIds(left: string, right: string): number {
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
}

export function createAgentRegistry(
  contributions: readonly AgentPanelContribution[],
): AgentRegistry {
  const ids = new Set<string>();
  const capabilityIds = new Set<string>();

  const copied = contributions.map((contribution) => {
    requireText(contribution.id, "id");
    requireText(contribution.capabilityId, "capabilityId");
    requireText(contribution.labelKey, "labelKey");

    if (!Number.isFinite(contribution.order)) {
      throw new Error("Agent contribution order must be finite");
    }
    if (ids.has(contribution.id)) {
      throw new Error(`Duplicate ID: ${contribution.id}`);
    }
    if (capabilityIds.has(contribution.capabilityId)) {
      throw new Error(
        `Duplicate capability ID: ${contribution.capabilityId}`,
      );
    }

    ids.add(contribution.id);
    capabilityIds.add(contribution.capabilityId);
    return {
      id: contribution.id,
      capabilityId: contribution.capabilityId,
      labelKey: contribution.labelKey,
      Icon: contribution.Icon,
      order: contribution.order,
      render: contribution.render,
    };
  });

  copied.sort(
    (left, right) =>
      left.order - right.order || compareAgentIds(left.id, right.id),
  );

  const all = Object.freeze(copied.map((contribution) => Object.freeze(contribution)));
  const byId = new Map(all.map((contribution) => [contribution.id, contribution]));

  return Object.freeze({
    all,
    find: (id: string) => byId.get(id),
    visibleFor: (successfulCapabilityIds: ReadonlySet<string>) =>
      Object.freeze(
        all.filter((contribution) =>
          successfulCapabilityIds.has(contribution.capabilityId),
        ),
      ),
  });
}

export const builtinAgentRegistry = createAgentRegistry([] as const);
