import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { classifyPwaRequest, shouldRegisterPwa } from "@/pwa/cachePolicy";

const serviceWorkerPath = fileURLToPath(
  new URL("../public/sw.js", import.meta.url),
);

describe("PWA cache policy", () => {
  it("caches only immutable public static assets", () => {
    expect(
      classifyPwaRequest(new URL("https://panel.example.test/assets/app-a1b2c3d4.js"), "GET"),
    ).toBe("cache-first");
    expect(
      classifyPwaRequest(new URL("https://panel.example.test/assets/app-a1b2c3d4.css"), "GET"),
    ).toBe("cache-first");
    expect(
      classifyPwaRequest(new URL("https://panel.example.test/fonts/GeistMono.woff2"), "GET"),
    ).toBe("cache-first");
    expect(
      classifyPwaRequest(new URL("https://panel.example.test/icons/miloco-192.png"), "GET"),
    ).toBe("cache-first");
  });

  it("never caches pages, APIs, tokens, history, or private photos", () => {
    for (const path of [
      "/",
      "/index.html",
      "/api/agents",
      "/outfit/moments/owner-1",
      "/outfit/media/asset-1?owner_person_id=owner-1",
      "/assets/app-a1b2c3d4.js?token=secret",
    ]) {
      expect(
        classifyPwaRequest(new URL(`https://panel.example.test${path}`), "GET"),
      ).toBe("network-only");
    }
    expect(
      classifyPwaRequest(new URL("https://panel.example.test/assets/app-a1b2c3d4.js"), "POST"),
    ).toBe("network-only");
  });

  it("registers only in secure browsers that expose service workers", () => {
    expect(shouldRegisterPwa({ isSecureContext: true, hasServiceWorker: true })).toBe(true);
    expect(shouldRegisterPwa({ isSecureContext: false, hasServiceWorker: true })).toBe(false);
    expect(shouldRegisterPwa({ isSecureContext: true, hasServiceWorker: false })).toBe(false);
  });

  it("keeps the service worker free of API, page, and media cache targets", () => {
    const serviceWorker = readFileSync(serviceWorkerPath, "utf8");

    expect(serviceWorker).not.toContain("/api/");
    expect(serviceWorker).not.toContain("index.html");
    expect(serviceWorker).not.toContain("outfit/media");
    expect(serviceWorker).not.toContain("cache.addAll");
  });
});
