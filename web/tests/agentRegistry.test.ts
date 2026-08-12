import { describe, expect, it } from "vitest";
import {
  createAgentPanelRegistry,
  type AgentPanelContribution,
} from "@/agents/registry";
import { createOutfitPanelContribution } from "@/components/outfit/OutfitPanel";

const outfitContribution: AgentPanelContribution = {
  id: "outfit",
  labelKey: "outfit.title",
  hintKey: "outfit.hint",
  capabilityId: "outfit_v2",
  Icon: () => null,
  render: () => null,
};

describe("Agent panel registry", () => {
  it("rejects duplicate contribution ids", () => {
    const registry = createAgentPanelRegistry();
    registry.register(outfitContribution);

    expect(() => registry.register(outfitContribution)).toThrow(
      "duplicate agent panel id",
    );
  });

  it("preserves explicit registration order", () => {
    const registry = createAgentPanelRegistry();
    registry.register(outfitContribution);
    registry.register({ ...outfitContribution, id: "cooking" });

    expect(registry.list().map((item) => item.id)).toEqual(["outfit", "cooking"]);
  });

  it("provides Outfit as an explicit contribution without changing host registry behavior", () => {
    const registry = createAgentPanelRegistry();
    registry.register(createOutfitPanelContribution());

    expect(registry.get("outfit")).toMatchObject({
      id: "outfit",
      capabilityId: "outfit_v2",
      labelKey: "outfit.title",
    });
  });
});
