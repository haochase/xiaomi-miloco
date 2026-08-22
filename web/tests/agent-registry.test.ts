import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  builtinAgentRegistry,
  createAgentRegistry,
} from "@/agents/registry";
import type { AgentPanelContribution } from "@/agents/types";

const TestIcon: AgentPanelContribution["Icon"] = () => null;

function contribution(
  overrides: Partial<AgentPanelContribution> = {},
): AgentPanelContribution {
  return {
    id: "calendar",
    capabilityId: "calendar.read",
    labelKey: "agents.calendar",
    Icon: TestIcon,
    order: 10,
    render: () => null,
    ...overrides,
  };
}

describe("agent contribution registry", () => {
  it.each([
    ["blank id", contribution({ id: "  " })],
    ["blank capability id", contribution({ capabilityId: "\t" })],
    ["blank label key", contribution({ labelKey: "\n" })],
    ["non-finite order", contribution({ order: Number.NaN })],
  ])("rejects a %s", (_label, item) => {
    expect(() => createAgentRegistry([item])).toThrow();
  });

  it("rejects duplicate IDs and capability IDs", () => {
    expect(() =>
      createAgentRegistry([
        contribution(),
        contribution({ capabilityId: "calendar.write" }),
      ]),
    ).toThrow(/duplicate id/i);
    expect(() =>
      createAgentRegistry([
        contribution(),
        contribution({ id: "calendar-write" }),
      ]),
    ).toThrow(/duplicate capability/i);
  });

  it("sorts deterministically by order and then ID", () => {
    const registry = createAgentRegistry([
      contribution({ id: "zeta", capabilityId: "zeta", order: 20 }),
      contribution({ id: "bravo", capabilityId: "bravo", order: 10 }),
      contribution({ id: "alpha", capabilityId: "alpha", order: 10 }),
    ]);

    expect(registry.all.map((item) => item.id)).toEqual([
      "alpha",
      "bravo",
      "zeta",
    ]);
  });

  it("sorts same-order IDs by code unit without host locale collation", () => {
    const localeCompare = vi
      .spyOn(String.prototype, "localeCompare")
      .mockImplementation(() => 0);

    try {
      const registry = createAgentRegistry([
        contribution({ id: "\u00e4", capabilityId: "umlaut", order: 10 }),
        contribution({ id: "a", capabilityId: "lower", order: 10 }),
        contribution({ id: "A", capabilityId: "upper", order: 10 }),
      ]);

      expect(registry.all.map((item) => item.id)).toEqual(["A", "a", "\u00e4"]);
      expect(localeCompare).not.toHaveBeenCalled();
    } finally {
      localeCompare.mockRestore();
    }
  });

  it("copies and freezes the registry so source mutation cannot change it", () => {
    const source = [contribution()];
    const registry = createAgentRegistry(source);

    (source[0] as { labelKey: string }).labelKey = "agents.changed";
    source.push(contribution({ id: "later", capabilityId: "later" }));

    expect(registry.all).toHaveLength(1);
    expect(registry.all[0].labelKey).toBe("agents.calendar");
    expect(Object.isFrozen(registry.all)).toBe(true);
    expect(Object.isFrozen(registry.all[0])).toBe(true);
  });

  it("keeps only the generic contribution contract fields", () => {
    const externalContribution = {
      ...contribution(),
      privateEndpoint: "not part of the registry",
    };
    const registry = createAgentRegistry([externalContribution]);

    expect(Object.keys(registry.all[0]).sort()).toEqual([
      "Icon",
      "capabilityId",
      "id",
      "labelKey",
      "order",
      "render",
    ]);
  });

  it("returns only panels whose capability IDs succeeded", () => {
    const registry = createAgentRegistry([
      contribution({ id: "visible", capabilityId: "capability.ready" }),
      contribution({ id: "hidden", capabilityId: "capability.pending" }),
    ]);

    expect(
      registry.visibleFor(new Set(["capability.ready"])).map((item) => item.id),
    ).toEqual(["visible"]);
  });

  it("starts with an explicitly empty builtin registry", () => {
    expect(builtinAgentRegistry.all).toEqual([]);
  });
});

describe("generic extension navigation boundary", () => {
  const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));
  const sidebarPath = fileURLToPath(
    new URL("../src/components/Sidebar.tsx", import.meta.url),
  );

  it("keeps App and Sidebar free of domain-specific outfit references", () => {
    expect(readFileSync(appPath, "utf8").toLowerCase()).not.toContain("outfit");
    expect(readFileSync(sidebarPath, "utf8").toLowerCase()).not.toContain("outfit");
  });

  it("adds exactly one generic agents entry to TABS", () => {
    const sidebar = readFileSync(sidebarPath, "utf8");

    expect(sidebar.match(/key:\s*"agents"/g)).toHaveLength(1);
    expect(sidebar).toContain('labelKey: "agents.title"');
  });

  it("routes global usage and devices jumps through the hash-aware tab handler", () => {
    const app = readFileSync(appPath, "utf8");

    expect(app).toMatch(
      /<OmniHealthBanner\s+onGoToConfig=\{\(\) => handleTabChange\("usage"\)\}\s*\/>/,
    );
    expect(app).toMatch(
      /<StatusRibbon[\s\S]*?onJumpDevices=\{\(\) => handleTabChange\("devices"\)\}/,
    );
  });
});
