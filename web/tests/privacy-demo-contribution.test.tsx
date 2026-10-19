import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createAgentRegistry } from "@/agents/registry";
import type { AgentPanelContribution } from "@/agents/types";
import { demoState } from "../../demo/privacy-space/src/demoData";
import { serializeDemoState } from "../../demo/privacy-space/src/demoSchema";

const Icon: AgentPanelContribution["Icon"] = () => null;
const privacyDemo: AgentPanelContribution = {
  id: "privacy-demo",
  capabilityId: "privacy_demo.synthetic",
  labelKey: "agents.privacyDemo.title",
  Icon,
  order: 50,
  render: () => <section>{demoState.outfit.candidates.join(" / ")}</section>,
};

describe("privacy demo as a generic Agent contribution", () => {
  it("remains hidden until its synthetic capability is explicitly published", () => {
    const registry = createAgentRegistry([privacyDemo]);
    expect(registry.visibleFor(new Set())).toEqual([]);
    expect(registry.visibleFor(new Set(["privacy_demo.synthetic"]))).toHaveLength(1);
  });

  it("renders only the synthetic structured view after publication", () => {
    const markup = renderToStaticMarkup(privacyDemo.render());
    expect(markup).toContain("浅色针织上衣 + 深色长裤");
    expect(markup).not.toMatch(/owner_id|device_id|api_key|raw_provider_answer|rec-synthetic/i);
    expect(serializeDemoState(demoState)).not.toMatch(/owner_id|device_id|api_key|raw_provider_answer/i);
  });
});
