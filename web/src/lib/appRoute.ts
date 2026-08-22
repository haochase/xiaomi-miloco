export type MainRoute = { readonly kind: "main" };
export type PerfRoute = { readonly kind: "perf" };
export type AgentsRoute = {
  readonly kind: "agents";
  readonly agentId?: string;
};

export type AppRoute = MainRoute | PerfRoute | AgentsRoute;

const mainRoute: MainRoute = Object.freeze({ kind: "main" });

export function parseAppRoute(hash: string): AppRoute {
  if (hash === "#perf") return { kind: "perf" };
  if (hash === "#/agents") return { kind: "agents" };

  const prefix = "#/agents/";
  if (!hash.startsWith(prefix)) return mainRoute;

  const encodedId = hash.slice(prefix.length);
  if (!encodedId || encodedId.includes("/")) return mainRoute;

  try {
    const agentId = decodeURIComponent(encodedId);
    return agentId && encodeURIComponent(agentId) === encodedId
      ? { kind: "agents", agentId }
      : mainRoute;
  } catch {
    return mainRoute;
  }
}

export function serializeAppRoute(route: AppRoute): string {
  switch (route.kind) {
    case "main":
      return "";
    case "perf":
      return "#perf";
    case "agents":
      if (route.agentId === undefined) return "#/agents";
      if (!route.agentId) {
        throw new Error("Agent route id must not be blank");
      }
      return `#/agents/${encodeURIComponent(route.agentId)}`;
  }
}
