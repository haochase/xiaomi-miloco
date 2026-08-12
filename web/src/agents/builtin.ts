import { createOutfitPanelContribution } from "@/components/outfit/OutfitPanel";
import type { AgentPanelRegistry } from "./registry";

export function registerBuiltInAgentPanels(registry: AgentPanelRegistry): void {
  registry.register(createOutfitPanelContribution());
}
