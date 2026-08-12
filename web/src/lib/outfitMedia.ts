import { resolveToken } from "@/api/client";

export type MediaAction = "share" | "download";
export type MediaActionResult = "shared" | "downloaded" | "cancelled";

export interface MediaCapabilities {
  hasShare: boolean;
  canShareFiles: boolean;
}

export interface OutfitPhotoActionInput {
  url: string;
  filename: string;
  title: string;
  action?: MediaAction;
}

interface FileShareNavigator {
  share?: (data: ShareData) => Promise<void>;
  canShare?: (data?: ShareData) => boolean;
}

export function selectMediaAction(capabilities: MediaCapabilities): MediaAction {
  return capabilities.hasShare && capabilities.canShareFiles ? "share" : "download";
}

export async function fetchOutfitPhoto(url: string): Promise<Blob> {
  const headers = new Headers();
  const token = resolveToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(url, { cache: "no-store", headers });
  if (!response.ok) {
    throw new Error(`photo request failed: ${response.status}`);
  }
  return response.blob();
}

export async function shareOrDownloadOutfitPhoto(
  input: OutfitPhotoActionInput,
): Promise<MediaActionResult> {
  const blob = await fetchOutfitPhoto(input.url);
  const file = new File([blob], input.filename, { type: blob.type });
  const navigatorWithFiles = navigator as FileShareNavigator;
  const action = input.action ?? selectMediaAction({
    hasShare: typeof navigatorWithFiles.share === "function",
    canShareFiles:
      typeof navigatorWithFiles.canShare === "function" &&
      navigatorWithFiles.canShare({ files: [file] }),
  });

  if (action === "share" && selectMediaAction({
    hasShare: typeof navigatorWithFiles.share === "function",
    canShareFiles:
      typeof navigatorWithFiles.canShare === "function" &&
      navigatorWithFiles.canShare({ files: [file] }),
  }) === "share") {
    try {
      await navigatorWithFiles.share?.({ title: input.title, files: [file] });
      return "shared";
    } catch (error) {
      if (isShareCancellation(error)) {
        return "cancelled";
      }
      throw error;
    }
  }

  downloadBlob(blob, input.filename);
  return "downloaded";
}

function downloadBlob(blob: Blob, filename: string): void {
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(href);
}

function isShareCancellation(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}
