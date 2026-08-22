import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  builtinAgentRegistry,
  loadBuiltinAgentCapabilityIds,
} from "@/agents/builtin";

const originalFetch = globalThis.fetch;
const originalToken = window.__MILOCO_TOKEN__;
const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));
const contributionPath = fileURLToPath(
  new URL("../src/agents/outfitContribution.tsx", import.meta.url),
);

const READY_CAPABILITY = {
  enabled: true,
  primary_person_configured: true,
  storage_ready: true,
  voice_ingress_configured: false,
  camera_allowlisted: false,
  last_provider_status: "never_called",
};

function capabilityResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = originalFetch;
  window.__MILOCO_TOKEN__ = originalToken;
});

describe("Outfit built-in contribution", () => {
  it("registers exactly one finite Outfit contribution", () => {
    expect(builtinAgentRegistry.all).toHaveLength(1);
    expect(builtinAgentRegistry.all[0]).toMatchObject({
      id: "outfit",
      capabilityId: "outfit_v2",
      labelKey: "agents.outfit.title",
    });
    expect(Number.isFinite(builtinAgentRegistry.all[0].order)).toBe(true);
  });

  it("exposes Outfit only after a strictly valid ready capability succeeds", async () => {
    window.__MILOCO_TOKEN__ = "test-token";
    globalThis.fetch = vi.fn(async () => capabilityResponse(READY_CAPABILITY)) as unknown as typeof fetch;

    const capabilityIds = await loadBuiltinAgentCapabilityIds();

    expect(capabilityIds).toEqual(new Set(["outfit_v2"]));
    expect(Object.isFrozen(capabilityIds)).toBe(true);
    expect(() => (capabilityIds as Set<string>).add("other")).toThrow(
      "capability IDs are immutable",
    );
    expect(builtinAgentRegistry.visibleFor(capabilityIds).map((item) => item.id)).toEqual([
      "outfit",
    ]);
  });

  it.each([
    ["an authentication failure", () => capabilityResponse({ detail: "no" }, 401)],
    ["a server failure", () => capabilityResponse({ detail: "no" }, 500)],
    ["an invalid capability response", () => capabilityResponse({ enabled: true })],
    [
      "a disabled capability",
      () => capabilityResponse({ ...READY_CAPABILITY, enabled: false }),
    ],
  ] as const)("keeps Outfit hidden after %s", async (_label, response) => {
    globalThis.fetch = vi.fn(async () => response()) as unknown as typeof fetch;

    const capabilityIds = await loadBuiltinAgentCapabilityIds();

    expect(capabilityIds).toEqual(new Set());
    expect(Object.isFrozen(capabilityIds)).toBe(true);
    expect(builtinAgentRegistry.visibleFor(capabilityIds)).toEqual([]);
  });
});

describe("generic application boundary", () => {
  it("keeps App generic while loading the built-in capability registry", () => {
    const app = readFileSync(appPath, "utf8");

    expect(app).toContain('from "./agents/builtin"');
    expect(app).toContain("loadBuiltinAgentCapabilityIds");
    expect(app.toLowerCase()).not.toContain("outfit");
  });

  it("keeps sensitive runtime selectors out of the contribution module", () => {
    const contribution = readFileSync(contributionPath, "utf8").toLowerCase();

    expect(contribution).not.toMatch(/https?:\/\/|token|device|remote script/);
  });
});
