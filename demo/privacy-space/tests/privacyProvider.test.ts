import { describe, expect, it } from "vitest";
import { readPrivacyFacts } from "../src/privacyProvider";

describe("readPrivacyFacts", () => {
  it("returns disabled unknown when no provider is configured", () => {
    expect(readPrivacyFacts(undefined)).toEqual({ status: "disabled", snapshot: null, errorCode: null });
  });

  it("isolates provider errors with a fixed code", () => {
    expect(readPrivacyFacts(() => { throw new Error("private details"); })).toEqual({ status: "failed", snapshot: null, errorCode: "provider_failed" });
  });

  it("rejects invalid provider snapshots without exposing raw errors", () => {
    expect(readPrivacyFacts(() => ({ snapshotId: "owner=secret" }))).toEqual({ status: "failed", snapshot: null, errorCode: "provider_invalid" });
  });
});
