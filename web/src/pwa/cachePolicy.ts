export type PwaRequestPolicy = "cache-first" | "network-only";

const HASHED_ASSET = /^\/assets\/.+-[A-Za-z0-9_-]{8,}\.(js|css)$/;

export function classifyPwaRequest(url: URL, method: string): PwaRequestPolicy {
  if (method !== "GET" || url.search) {
    return "network-only";
  }
  const immutableAsset = HASHED_ASSET.test(url.pathname);
  const publicStatic =
    url.pathname.startsWith("/fonts/") || url.pathname.startsWith("/icons/");
  return immutableAsset || publicStatic ? "cache-first" : "network-only";
}

export function shouldRegisterPwa(input: {
  isSecureContext: boolean;
  hasServiceWorker: boolean;
}): boolean {
  return input.isSecureContext && input.hasServiceWorker;
}
