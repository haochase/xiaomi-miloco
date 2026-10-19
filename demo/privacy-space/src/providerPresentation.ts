type ProviderDisplay = { status: "disabled" | "ready" | "failed"; label: string; errorCode: string | null };

export function providerPresentation(result: ProviderDisplay): string {
  if (result.status === "disabled") return "事实源未启用";
  if (result.status === "ready") return "事实源可用";
  return "事实源暂不可用";
}
