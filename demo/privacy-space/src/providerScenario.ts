export type ProviderScenario = "disabled" | "fixture" | "failed";

export function readProviderScenario(scenario: ProviderScenario) {
  if (scenario === "disabled") return { status: "disabled", label: "事实源未启用" } as const;
  if (scenario === "failed") return { status: "failed", label: "事实源暂不可用" } as const;
  return { status: "ready", label: "事实源可用" } as const;
}
