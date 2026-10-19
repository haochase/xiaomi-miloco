export type DemoRefreshState = {
  status: "idle" | "loading" | "succeeded" | "failed";
  errorCode: "fixture_unavailable" | null;
};

export function startRefresh(state: DemoRefreshState): DemoRefreshState {
  return state.status === "loading" ? state : { status: "loading", errorCode: null };
}

export function finishRefresh(_state: DemoRefreshState, succeeded: boolean): DemoRefreshState {
  return succeeded ? { status: "succeeded", errorCode: null } : { status: "failed", errorCode: "fixture_unavailable" };
}
