import { describe, expect, it } from "vitest";
import { finishRefresh, startRefresh, type DemoRefreshState } from "../src/refreshState";

describe("refresh state", () => {
  it("moves through loading to succeeded", () => {
    const loading = startRefresh({ status: "idle", errorCode: null });
    expect(loading).toEqual({ status: "loading", errorCode: null });
    expect(finishRefresh(loading, true)).toEqual({ status: "succeeded", errorCode: null });
  });

  it("records a fixed error code without raw details", () => {
    const loading: DemoRefreshState = { status: "loading", errorCode: null };
    expect(finishRefresh(loading, false)).toEqual({ status: "failed", errorCode: "fixture_unavailable" });
  });
});
