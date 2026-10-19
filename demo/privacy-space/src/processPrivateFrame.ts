import { lstat, readFile, unlink } from "node:fs/promises";
import { isAbsolute, relative, resolve } from "node:path";
import { redactRgbaFrame, type RedactionRegion } from "./redactFrame";

type ProcessRequest = {
  path: string;
  temporaryRoot: string;
  width: number;
  height: number;
  regions: RedactionRegion[];
  statFrame?: (path: string) => Promise<{ size: number; isSymbolicLink(): boolean; isFile(): boolean }>;
  readFrame?: (path: string) => Promise<Uint8Array>;
};

const MAX_FRAME_BYTES = 16 * 1024 * 1024;

type ProcessResult = {
  status: "processed" | "failed";
  errorCode: "privacy_processing_failed" | "temporary_frame_cleanup_failed" | null;
  temporaryFrameCleared: boolean;
  /** Local rendering only; never serialize into logs, audit records, or API responses. */
  redactedPixels: Uint8ClampedArray | null;
};

export async function processPrivateRgbaFrame(request: ProcessRequest): Promise<ProcessResult> {
  const source = resolve(request.path);
  const root = resolve(request.temporaryRoot);
  const inside = relative(root, source);
  if (!isAbsolute(request.path) || inside === "" || inside.startsWith("..") || isAbsolute(inside)) {
    return { status: "failed", errorCode: "privacy_processing_failed", temporaryFrameCleared: false, redactedPixels: null };
  }

  let redactedPixels: Uint8ClampedArray | null = null;
  let errorCode: ProcessResult["errorCode"] = null;
  let temporaryFrameCleared = false;
  try {
    const metadata = await (request.statFrame ?? lstat)(source);
    const expectedBytes = request.width * request.height * 4;
    if (
      !metadata.isFile() || metadata.isSymbolicLink() ||
      !Number.isSafeInteger(expectedBytes) || expectedBytes <= 0 ||
      expectedBytes > MAX_FRAME_BYTES || metadata.size !== expectedBytes
    ) throw new Error("invalid frame metadata");
    const bytes = await (request.readFrame ?? readFile)(source);
    const result = redactRgbaFrame(
      { width: request.width, height: request.height, pixels: new Uint8ClampedArray(bytes) },
      request.regions,
    );
    redactedPixels = result.pixels;
  } catch {
    errorCode = "privacy_processing_failed";
  } finally {
    try {
      await unlink(source);
      temporaryFrameCleared = true;
    } catch {
      errorCode = "temporary_frame_cleanup_failed";
      redactedPixels = null;
    }
  }

  return {
    status: errorCode === null ? "processed" : "failed",
    errorCode,
    temporaryFrameCleared,
    redactedPixels,
  };
}
