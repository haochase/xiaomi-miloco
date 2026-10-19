import { describe, expect, it } from "vitest";
import { providerPresentation } from "../src/providerPresentation";

describe("providerPresentation", () => {
  it("maps provider states to low-sensitivity panel labels", () => {
    expect(providerPresentation({ status: "disabled", label: "事实源未启用", errorCode: null })).toEqual("事实源未启用");
    expect(providerPresentation({ status: "ready", label: "事实源可用", errorCode: null })).toEqual("事实源可用");
    expect(providerPresentation({ status: "failed", label: "事实源暂不可用", errorCode: "provider_failed" })).toEqual("事实源暂不可用");
  });
});
