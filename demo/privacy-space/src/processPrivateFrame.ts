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
  deleteFrame?: (path: string) => Promise<void>;
};

const MAX_FRAME_BYTES = 16 * 1024 * 1024;

type ProcessResult = {
  status: "processed" | "failed";
  errorCode: "privacy_processing_failed" | "temporary_frame_cleanup_failed" | null;
  temporaryFrameCleared: boolean;
  /** Explicit local rendering access; omitted from JSON and object spread. */
  getRedactedPixels(): Uint8ClampedArray | null;
  toJSON(): Pick<ProcessResult, "status" | "errorCode" | "temporaryFrameCleared">;
};

export async function processPrivateRgbaFrame(request: ProcessRequest): Promise<ProcessResult> {
  const source = resolve(request.path);
  const root = resolve(request.temporaryRoot);
  const inside = relative(root, source);
  if (!isAbsolute(request.path) || inside === "" || inside.startsWith("..") || isAbsolute(inside)) {
    return makeResult("failed", "privacy_processing_failed", false, null);
  }

  let redactedPixels: Uint8ClampedArray | null = null;
  let errorCode: ProcessResult["errorCode"] = null;
  let temporaryFrameCleared = false;
  let canDeleteSource = false;
  try {
    const metadata = await (request.statFrame ?? lstat)(source);
    if (!metadata.isFile() || metadata.isSymbolicLink()) {
      throw new Error("invalid file type");
    }
    canDeleteSource = true;
    const expectedBytes = request.width * request.height * 4;
    if (
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
    if (canDeleteSource) {
      try {
        await (request.deleteFrame ?? unlink)(source);
        temporaryFrameCleared = true;
      } catch {
        errorCode = "temporary_frame_cleanup_failed";
        redactedPixels = null;
      }
    }
  }

  return makeResult(errorCode === null ? "processed" : "failed", errorCode, temporaryFrameCleared, redactedPixels);
}

function makeResult(
  status: ProcessResult["status"],
  errorCode: ProcessResult["errorCode"],
  temporaryFrameCleared: boolean,
  redactedPixels: Uint8ClampedArray | null,
): ProcessResult {
  const result = {
    status,
    errorCode,
    temporaryFrameCleared,
  } as ProcessResult;
  Object.defineProperties(result, {
    getRedactedPixels: {
      value: () => redactedPixels === null ? null : new Uint8ClampedArray(redactedPixels),
      enumerable: false,
    },
    toJSON: {
      value: () => ({ status, errorCode, temporaryFrameCleared }),
      enumerable: false,
    },
  });
  return result;
}
