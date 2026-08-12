import type { AgentPanelContribution } from "./types";

export type { AgentPanelContribution } from "./types";

export interface AgentPanelRegistry {
  register: (item: AgentPanelContribution) => void;
  list: () => AgentPanelContribution[];
  get: (id: string) => AgentPanelContribution | undefined;
}

export function createAgentPanelRegistry(): AgentPanelRegistry {
  const items = new Map<string, AgentPanelContribution>();

  return {
    register(item) {
      if (items.has(item.id)) {
        throw new Error("duplicate agent panel id");
      }
      items.set(item.id, item);
    },
    list() {
      return [...items.values()];
    },
    get(id) {
      return items.get(id);
    },
  };
}

export const agentPanelRegistry = createAgentPanelRegistry();
