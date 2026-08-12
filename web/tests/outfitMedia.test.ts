import { afterEach, describe, expect, it, vi } from "vitest";
import {
  shareOrDownloadOutfitPhoto,
  selectMediaAction,
} from "@/lib/outfitMedia";

const originalFetch = globalThis.fetch;
const originalNavigator = globalThis.navigator;
const originalDocument = globalThis.document;

afterEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = originalFetch;
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: originalNavigator,
  });
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: originalDocument,
  });
});

function mockPhotoResponse(status = 200): void {
  globalThis.fetch = vi.fn(async () =>
    new Response(new Blob(["photo"], { type: "image/jpeg" }), { status }),
  ) as unknown as typeof fetch;
}

describe("Outfit media actions", () => {
  it("uses share only when file sharing is supported", () => {
    expect(selectMediaAction({ hasShare: true, canShareFiles: true })).toBe("share");
    expect(selectMediaAction({ hasShare: true, canShareFiles: false })).toBe("download");
    expect(selectMediaAction({ hasShare: false, canShareFiles: false })).toBe("download");
  });

  it("downloads on an explicit save command without claiming album sync", async () => {
    mockPhotoResponse();
    const click = vi.fn();
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: {},
    });
    Object.defineProperty(globalThis, "document", {
      configurable: true,
      value: { createElement: vi.fn(() => ({ click })) },
    });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:outfit-photo");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);

    await expect(
      shareOrDownloadOutfitPhoto({
        url: "/api/outfit/media/asset-1",
        filename: "outfit.jpg",
        title: "Outfit moment",
        action: "download",
      }),
    ).resolves.toBe("downloaded");
    expect(click).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledWith("blob:outfit-photo");
  });

  it("treats a share cancellation as a non-error result", async () => {
    mockPhotoResponse();
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: {
        canShare: vi.fn(() => true),
        share: vi.fn(async () => {
          throw Object.assign(new Error("cancelled"), { name: "AbortError" });
        }),
      },
    });

    await expect(
      shareOrDownloadOutfitPhoto({
        url: "/api/outfit/media/asset-1",
        filename: "outfit.jpg",
        title: "Outfit moment",
        action: "share",
      }),
    ).resolves.toBe("cancelled");
  });

  it.each([401, 404])("reports inaccessible media (%s)", async (status) => {
    mockPhotoResponse(status);

    await expect(
      shareOrDownloadOutfitPhoto({
        url: "/api/outfit/media/asset-1",
        filename: "outfit.jpg",
        title: "Outfit moment",
        action: "download",
      }),
    ).rejects.toThrow(`photo request failed: ${status}`);
  });
});
