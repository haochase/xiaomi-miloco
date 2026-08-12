export type AppRoute =
  | { tab: "now" }
  | { tab: "perf" }
  | {
      tab: "agents";
      agentId?: string;
      view?: "moments" | "moment";
      momentId?: string;
    };

const MAX_ROUTE_SEGMENT_LENGTH = 128;

export function parseAppRoute(hash: string): AppRoute {
  if (hash === "#perf") {
    return { tab: "perf" };
  }
  if (hash === "#/agents") {
    return { tab: "agents" };
  }
  if (!hash.startsWith("#/agents/")) {
    return { tab: "now" };
  }

  const segments = hash.slice("#/agents/".length).split("/");
  const agentId = decodeRouteSegment(segments[0]);
  if (agentId === null) {
    return { tab: "now" };
  }
  if (segments.length === 1) {
    return { tab: "agents", agentId };
  }
  if (segments.length === 2 && segments[1] === "moments") {
    return { tab: "agents", agentId, view: "moments" };
  }
  if (segments.length !== 3 || segments[1] !== "moments") {
    return { tab: "now" };
  }
  const momentId = decodeRouteSegment(segments[2]);
  if (momentId === null) {
    return { tab: "now" };
  }
  return { tab: "agents", agentId, view: "moment", momentId };
}

/** True when a route can be rendered without loading the host-control data. */
export function isAgentRoute(route: AppRoute): route is Extract<AppRoute, { tab: "agents" }> {
  return route.tab === "agents";
}

/** Make an isolated Outfit sidecar land on its only supported panel route. */
export function resolvePanelRoute(
  route: AppRoute,
  options: { outfitSidecar: boolean },
): AppRoute {
  if (options.outfitSidecar && route.tab === "now") {
    return { tab: "agents", agentId: "outfit" };
  }
  return route;
}

export function formatAgentRoute(agentId: string): string {
  return `#/agents/${encodeRouteSegment(agentId)}`;
}

export function formatAgentMomentRoute(agentId: string, momentId: string): string {
  return `${formatAgentMomentsRoute(agentId)}/${encodeRouteSegment(momentId)}`;
}

export function formatAgentMomentsRoute(agentId: string): string {
  return `${formatAgentRoute(agentId)}/moments`;
}

function decodeRouteSegment(segment: string | undefined): string | null {
  if (!segment) {
    return null;
  }
  try {
    const decoded = decodeURIComponent(segment);
    if (!decoded || decoded.length > MAX_ROUTE_SEGMENT_LENGTH) {
      return null;
    }
    return decoded;
  } catch {
    return null;
  }
}

function encodeRouteSegment(segment: string): string {
  if (!segment || segment.length > MAX_ROUTE_SEGMENT_LENGTH) {
    throw new Error("route segment must be between 1 and 128 characters");
  }
  return encodeURIComponent(segment);
}
