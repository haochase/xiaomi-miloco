import { describe, expect, it } from "vitest";
import { summarizeEvidence } from "../src/evidenceSummary";

describe("summarizeEvidence", () => {
  it("shows active source and fresh facts only when both are true", () => {
    expect(summarizeEvidence("ready", "fresh")).toBe("事实源可用 · 事实有效");
  });

  it("keeps disabled or failed sources from claiming fresh facts", () => {
    expect(summarizeEvidence("disabled", "fresh")).toBe("事实源未启用 · 事实未知");
    expect(summarizeEvidence("failed", "fresh")).toBe("事实源暂不可用 · 事实未知");
  });
});
