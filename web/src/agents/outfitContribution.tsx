import { IconLightbulb } from "@/lib/icons";
import { OutfitPanel } from "@/components/agents/outfit/OutfitPanel";
import type { AgentPanelContribution } from "./types";

export const outfitContribution: AgentPanelContribution = {
  id: "outfit",
  capabilityId: "outfit_v2",
  labelKey: "agents.outfit.title",
  Icon: IconLightbulb,
  order: 40,
  render: () => <OutfitPanel />,
};
