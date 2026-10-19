import { readPrivacyFacts } from "./privacyProvider";

export type ProviderScenario = "disabled" | "fixture" | "failed";

export function readProviderScenario(scenario: ProviderScenario) {
  const result = scenario === "disabled"
    ? readPrivacyFacts(undefined)
    : scenario === "failed"
      ? readPrivacyFacts(() => { throw new Error("provider failure"); })
      : readPrivacyFacts(() => ({ snapshotId: "fixture-snapshot", freshness: "unknown", rooms: [], anonymousPeopleCount: null, outfitSummary: [] }));
  if (result.status === "disabled") return { status: "disabled", label: "事实源未启用", errorCode: null } as const;
  if (result.status === "failed") return { status: "failed", label: "事实源暂不可用", errorCode: result.errorCode } as const;
  return { status: "ready", label: "事实源可用", errorCode: null } as const;
}
