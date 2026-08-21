import { afterEach, describe, expect, it, vi } from "vitest";
import {
  requestVisualReview,
  type VisualReviewErrorCode,
  type VisualReviewStatus,
  type VisualReviewTrigger,
} from "@/api";

const originalFetch = globalThis.fetch;

const VALID_TERMINAL_RESPONSES = [
  ["completed", null],
  ["rejected", "explicit_trigger_required"],
  ["rejected", "session_expired"],
  ["rejected", "concurrent_request_limit"],
  ["rejected", "model_call_limit"],
  ["rejected", "token_budget_exceeded"],
  ["rejected", "usage_unavailable"],
  ["rejected", "provider_error_limit"],
  ["rejected", "session_start_in_future"],
  ["rejected", "session_start_mismatch"],
  ["capture_failed", "capture_failed"],
  ["capture_failed", "capture_timeout"],
  ["capture_failed", "overall_timeout"],
  ["provider_failed", "provider_failed"],
  ["provider_failed", "provider_timeout"],
  ["provider_failed", "overall_timeout"],
  ["provider_failed", "usage_unavailable"],
  ["provider_failed", "token_budget_exceeded"],
  ["cleanup_failed", "temporary_media_cleanup_failed"],
] as const satisfies ReadonlyArray<
  readonly [VisualReviewStatus, VisualReviewErrorCode | null]
>;

const INVALID_TERMINAL_RESPONSES = [
  ["completed", "provider_failed"],
  ["rejected", null],
  ["rejected", "overall_timeout"],
  ["capture_failed", "provider_timeout"],
  ["provider_failed", "capture_timeout"],
  ["cleanup_failed", "overall_timeout"],
  ["provider_failed", "E:\\synthetic\\frames\\capture.jpg"],
  ["unknown", null],
] as const;

afterEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = originalFetch;
});

describe("requestVisualReview — active panel trigger contract", () => {
  it("posts only the selected recommendation and configured camera", async () => {
    let requestUrl: RequestInfo | URL | undefined;
    let requestInit: RequestInit | undefined;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requestUrl = input;
      requestInit = init;
      return new Response(
        JSON.stringify({ status: "completed", error_code: null }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }) as unknown as typeof fetch;

    const trigger: VisualReviewTrigger = {
      triggerId: "trigger-1",
      recommendationId: "recommendation-1",
      deviceId: "camera-1",
    };

    await expect(requestVisualReview(trigger)).resolves.toEqual({
      status: "completed",
      errorCode: null,
    });
    expect(requestUrl).toBe("/api/outfit/try-on/review");
    expect(requestInit?.method).toBe("POST");
    expect(JSON.parse(String(requestInit?.body))).toEqual({
      trigger_id: "trigger-1",
      recommendation_id: "recommendation-1",
      device_id: "camera-1",
    });
  });

  it("maps sanitized failure responses without exposing media or provider details", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({ status: "provider_failed", error_code: "provider_timeout" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ) as unknown as typeof fetch;

    await expect(
      requestVisualReview({
        triggerId: "trigger-2",
        recommendationId: "recommendation-2",
        deviceId: "camera-1",
      }),
    ).resolves.toEqual({
      status: "provider_failed",
      errorCode: "provider_timeout",
    });
  });

  it.each(INVALID_TERMINAL_RESPONSES)(
    "rejects the mismatched or unknown terminal response %s / %s",
    async (status, errorCode) => {
      globalThis.fetch = vi.fn(async () =>
        new Response(JSON.stringify({ status, error_code: errorCode }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ) as unknown as typeof fetch;

      await expect(
        requestVisualReview({
          triggerId: "trigger-3",
          recommendationId: "recommendation-3",
          deviceId: "camera-1",
        }),
      ).rejects.toThrow("invalid visual review response");
    },
  );

  it.each(VALID_TERMINAL_RESPONSES)(
    "accepts the backend terminal response %s / %s",
    async (status, errorCode) => {
      globalThis.fetch = vi.fn(async () =>
        new Response(
          JSON.stringify({ status, error_code: errorCode }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ) as unknown as typeof fetch;

      await expect(
        requestVisualReview({
          triggerId: "trigger-4",
          recommendationId: "recommendation-4",
          deviceId: "camera-1",
        }),
      ).resolves.toEqual({ status, errorCode });
    },
  );
});
