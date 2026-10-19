import { parsePrivacyFactsSnapshot, type PrivacyFactsSnapshot } from "./privacySnapshot";

export type PrivacyProvider = () => unknown;
export type PrivacyReadResult = {
  status: "disabled" | "ready" | "failed";
  snapshot: PrivacyFactsSnapshot | null;
  errorCode: "provider_failed" | "provider_invalid" | null;
};

export function readPrivacyFacts(provider: PrivacyProvider | undefined): PrivacyReadResult {
  if (!provider) return { status: "disabled", snapshot: null, errorCode: null };
  try {
    return { status: "ready", snapshot: parsePrivacyFactsSnapshot(provider()), errorCode: null };
  } catch (error) {
    const code = error instanceof Error && error.message === "invalid privacy facts snapshot" ? "provider_invalid" : "provider_failed";
    return { status: "failed", snapshot: null, errorCode: code };
  }
}
