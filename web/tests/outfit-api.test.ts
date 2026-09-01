import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getOutfitCapability,
  getOutfitUsageToday,
  getOutfitWardrobe,
  requestVisualReview,
  type VisualReviewErrorCode,
  type VisualReviewStatus,
  type VisualReviewTrigger,
} from "@/api/outfit";

const originalFetch = globalThis.fetch;
const originalToken = window.__MILOCO_TOKEN__;

const VALID_CAPABILITY = {
  enabled: true,
  primary_person_configured: true,
  storage_ready: true,
  voice_ingress_configured: false,
  camera_allowlisted: true,
  last_provider_status: "last_success",
};

const VALID_USAGE = {
  date: "2026-08-22",
  timezone: "Asia/Shanghai",
  call_count: 2,
  input_tokens: 13,
  output_tokens: 5,
  estimated_total_tokens: 21,
  complete: true,
};

const VALID_PENDING_DRAFTS = [
  {
    draft_id: "draft-1",
    name: "Navy shirt",
    category: "top",
    source_types: ["photo"],
    status: "pending",
  },
];

const VALID_AVAILABLE_ITEMS = [
  {
    item_id: "item-1",
    name: "Black trousers",
    category: "bottom",
    source_types: ["manual"],
    status: "confirmed",
    availability: "available",
  },
];

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

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
  window.__MILOCO_TOKEN__ = originalToken;
});

describe("Outfit capability and usage read contracts", () => {
  it("gets the exact capability snapshot through a header-only GET", async () => {
    let requestUrl: RequestInfo | URL | undefined;
    let requestInit: RequestInit | undefined;
    window.__MILOCO_TOKEN__ = "test-token";
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requestUrl = input;
      requestInit = init;
      return jsonResponse(VALID_CAPABILITY);
    }) as unknown as typeof fetch;

    await expect(getOutfitCapability()).resolves.toEqual({
      enabled: true,
      primaryPersonConfigured: true,
      storageReady: true,
      voiceIngressConfigured: false,
      cameraAllowlisted: true,
      lastProviderStatus: "last_success",
    });
    expect(requestUrl).toBe("/api/outfit/capability");
    expect(requestInit?.method).toBe("GET");
    expect(requestInit?.body).toBeUndefined();
    expect(new Headers(requestInit?.headers).get("Authorization")).toBe(
      "Bearer test-token",
    );
  });

  it.each([
    ["an extra field", { ...VALID_CAPABILITY, owner_person_id: "private" }],
    ["a missing field", { ...VALID_CAPABILITY, storage_ready: undefined }],
    ["a non-boolean flag", { ...VALID_CAPABILITY, enabled: "yes" }],
    ["an unsupported provider status", { ...VALID_CAPABILITY, last_provider_status: "busy" }],
    ["a non-object payload", []],
  ] as const)("rejects capability payloads with %s", async (_label, payload) => {
    globalThis.fetch = vi.fn(async () => jsonResponse(payload)) as unknown as typeof fetch;

    await expect(getOutfitCapability()).rejects.toThrow(
      "invalid outfit capability response",
    );
  });

  it("gets an incomplete usage snapshot as explicit unknown token values", async () => {
    let requestUrl: RequestInfo | URL | undefined;
    let requestInit: RequestInit | undefined;
    window.__MILOCO_TOKEN__ = "usage-token";
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requestUrl = input;
      requestInit = init;
      return jsonResponse({
        ...VALID_USAGE,
        input_tokens: null,
        output_tokens: null,
        estimated_total_tokens: null,
        complete: false,
      });
    }) as unknown as typeof fetch;

    await expect(getOutfitUsageToday()).resolves.toEqual({
      date: "2026-08-22",
      timezone: "Asia/Shanghai",
      callCount: 2,
      inputTokens: null,
      outputTokens: null,
      estimatedTotalTokens: null,
      complete: false,
    });
    expect(requestUrl).toBe("/api/outfit/admin/usage/today");
    expect(requestInit?.method).toBe("GET");
    expect(requestInit?.body).toBeUndefined();
    expect(new Headers(requestInit?.headers).get("Authorization")).toBe(
      "Bearer usage-token",
    );
  });

  it.each([
    ["an extra field", { ...VALID_USAGE, private_model: "hidden" }],
    ["an invalid date", { ...VALID_USAGE, date: "2026-02-30" }],
    ["a different timezone", { ...VALID_USAGE, timezone: "UTC" }],
    ["a negative count", { ...VALID_USAGE, call_count: -1 }],
    ["a fractional token count", { ...VALID_USAGE, input_tokens: 0.5 }],
    ["an unsafe integer", { ...VALID_USAGE, output_tokens: Number.MAX_SAFE_INTEGER + 1 }],
    ["a complete response with a null token", { ...VALID_USAGE, input_tokens: null }],
    [
      "an incomplete response with a known token",
      { ...VALID_USAGE, input_tokens: null, output_tokens: 2, estimated_total_tokens: null, complete: false },
    ],
    ["a non-object payload", []],
  ] as const)("rejects usage payloads with %s", async (_label, payload) => {
    globalThis.fetch = vi.fn(async () => jsonResponse(payload)) as unknown as typeof fetch;

    await expect(getOutfitUsageToday()).rejects.toThrow(
      "invalid outfit usage response",
    );
  });
});

describe("Outfit wardrobe read contracts", () => {
  it("reads the two owner-free wardrobe lists through header-only GET requests", async () => {
    const requests: Array<[RequestInfo | URL, RequestInit | undefined]> = [];
    window.__MILOCO_TOKEN__ = "wardrobe-token";
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push([input, init]);
      return jsonResponse(
        input === "/api/outfit/wardrobe/drafts"
          ? VALID_PENDING_DRAFTS
          : VALID_AVAILABLE_ITEMS,
      );
    }) as unknown as typeof fetch;

    await expect(getOutfitWardrobe()).resolves.toEqual({
      pendingDrafts: [
        {
          draftId: "draft-1",
          name: "Navy shirt",
          category: "top",
          sourceTypes: ["photo"],
          status: "pending",
        },
      ],
      availableItems: [
        {
          itemId: "item-1",
          name: "Black trousers",
          category: "bottom",
          sourceTypes: ["manual"],
          status: "confirmed",
          availability: "available",
        },
      ],
    });
    expect(requests.map(([url]) => url)).toEqual([
      "/api/outfit/wardrobe/drafts",
      "/api/outfit/wardrobe/items/available",
    ]);
    for (const [, init] of requests) {
      expect(init?.method).toBe("GET");
      expect(init?.body).toBeUndefined();
      expect(new Headers(init?.headers).get("Authorization")).toBe(
        "Bearer wardrobe-token",
      );
    }
  });

  it.each([
    ["a source reference", [{ ...VALID_PENDING_DRAFTS[0], source_reference: "private" }], VALID_AVAILABLE_ITEMS],
    ["a wrong draft status", [{ ...VALID_PENDING_DRAFTS[0], status: "confirmed" }], VALID_AVAILABLE_ITEMS],
    ["a wrong item availability", VALID_PENDING_DRAFTS, [{ ...VALID_AVAILABLE_ITEMS[0], availability: "laundry" }]],
    ["a non-array payload", {}, VALID_AVAILABLE_ITEMS],
  ] as const)("rejects wardrobe payloads with %s", async (_label, drafts, items) => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) =>
      jsonResponse(input === "/api/outfit/wardrobe/drafts" ? drafts : items),
    ) as unknown as typeof fetch;

    await expect(getOutfitWardrobe()).rejects.toThrow("invalid outfit wardrobe response");
  });
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
