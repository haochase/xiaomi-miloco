type SourceStatus = "disabled" | "ready" | "failed";
type Freshness = "fresh" | "unknown";

export function summarizeEvidence(sourceStatus: SourceStatus, freshness: Freshness): string {
  const source = sourceStatus === "ready" ? "事实源可用" : sourceStatus === "failed" ? "事实源暂不可用" : "事实源未启用";
  return `${source} · ${sourceStatus === "ready" && freshness === "fresh" ? "事实有效" : "事实未知"}`;
}
