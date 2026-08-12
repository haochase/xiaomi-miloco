import { describe, expect, it } from "vitest";
import { registerBuiltInAgentPanels } from "@/agents/builtin";
import { createAgentPanelRegistry } from "@/agents/registry";

describe("built-in agent panels", () => {
  it("registers Outfit through the generic registry without changing its capability id", () => {
    const registry = createAgentPanelRegistry();

    registerBuiltInAgentPanels(registry);

    expect(registry.get("outfit")).toMatchObject({
      id: "outfit",
      capabilityId: "outfit_v2",
    });
  });
});
