import { describe, expect, it } from "vitest";
import {
  enabledAgentCapabilityIds,
  listVisibleAgentPanelContributions,
  type AgentCapabilitySnapshot,
} from "@/agents/capabilities";
import {
  createAgentPanelRegistry,
  type AgentPanelContribution,
} from "@/agents/registry";

const outfitContribution: AgentPanelContribution = {
  id: "outfit",
  labelKey: "outfit.title",
  hintKey: "outfit.hint",
  capabilityId: "outfit_v2",
  Icon: () => null,
  render: () => null,
};

describe("Agent capability visibility", () => {
  it("shows only registered contributions with an enabled capability", () => {
    const registry = createAgentPanelRegistry();
    registry.register(outfitContribution);
    registry.register({ ...outfitContribution, id: "cooking", capabilityId: "cooking" });

    const disabled: AgentCapabilitySnapshot[] = [];
    const enabled: AgentCapabilitySnapshot[] = [
      { id: "outfit_v2", enabled: true, api_version: "v1" },
      { id: "cooking", enabled: false, api_version: "v1" },
    ];

    expect(listVisibleAgentPanelContributions(registry, disabled)).toEqual([]);
    expect(
      listVisibleAgentPanelContributions(registry, enabled).map((item) => item.id),
    ).toEqual(["outfit"]);
  });

  it("only treats explicitly enabled snapshot entries as visible", () => {
    expect(
      enabledAgentCapabilityIds([
        { id: "outfit_v2", enabled: false, api_version: "v1" },
        { id: "outfit_v2", enabled: true, api_version: "v1" },
      ]),
    ).toEqual(new Set(["outfit_v2"]));
  });
});
