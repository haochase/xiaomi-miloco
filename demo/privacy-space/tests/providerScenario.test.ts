import { describe, expect, it } from "vitest";
import { readProviderScenario } from "../src/providerScenario";

describe("readProviderScenario", () => {
  it("maps disabled provider to unknown state", () => {
    expect(readProviderScenario("disabled")).toEqual({ status: "disabled", label: "事实源未启用", errorCode: null });
  });

  it("maps fixture provider to ready without exposing snapshot details", () => {
    expect(readProviderScenario("fixture")).toEqual({ status: "ready", label: "事实源可用", errorCode: null });
  });

  it("maps failure to a fixed low-sensitivity label", () => {
    expect(readProviderScenario("failed")).toEqual({ status: "failed", label: "事实源暂不可用", errorCode: "provider_failed" });
  });
});
