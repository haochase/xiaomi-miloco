import { access, unlink } from "node:fs/promises";
import { isAbsolute, normalize, relative, resolve } from "node:path";

export type PrivacyProcessingResult = {
  status: "processed" | "failed";
  errorCode: "privacy_processing_failed" | "temporary_frame_cleanup_failed" | null;
  temporaryFrameCleared: boolean;
  frameCount: number;
  summary: string;
};

export type PrivacyFrameProcessorOptions = {
  fail?: boolean;
  deleteFrame?: (framePath: string) => Promise<void>;
};

export class PrivacyFrameProcessor {
  constructor(
    private readonly options: PrivacyFrameProcessorOptions = {},
    private readonly temporaryRoot: string,
  ) {}

  async process(framePath: string): Promise<PrivacyProcessingResult> {
    let status: PrivacyProcessingResult["status"] = "processed";
    let errorCode: PrivacyProcessingResult["errorCode"] = null;
    let temporaryFrameCleared = false;
    const resolvedFrame = normalize(resolve(framePath));
    const resolvedRoot = normalize(resolve(this.temporaryRoot));
    const relativeFrame = relative(resolvedRoot, resolvedFrame);
    const allowedPath = isAbsolute(resolvedFrame) && relativeFrame !== "" && !relativeFrame.startsWith("..") && !isAbsolute(relativeFrame);

    try {
      if (!allowedPath) {
        throw new Error("temporary frame path is outside the controlled root");
      }
      await access(resolvedFrame);
      if (this.options.fail) {
        throw new Error("synthetic privacy failure");
      }
    } catch {
      status = "failed";
      errorCode = "privacy_processing_failed";
    } finally {
      try {
        if (allowedPath) {
          await (this.options.deleteFrame ?? unlink)(resolvedFrame);
          temporaryFrameCleared = true;
        }
      } catch {
        status = "failed";
        errorCode = "temporary_frame_cleanup_failed";
      }
    }

    return {
      status,
      errorCode,
      temporaryFrameCleared,
      frameCount: 1,
      summary:
        status === "processed"
          ? "合成画面已完成本地隐私摘要处理"
          : "隐私摘要处理未完成",
    };
  }
}
