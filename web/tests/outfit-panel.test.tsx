import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import i18n from "@/i18n";
import {
  OutfitPanelReadyContent,
  resolveOutfitPanelPhase,
  type OutfitPanelLoadState,
  type OutfitPanelView,
} from "@/components/agents/outfit/OutfitPanel";
import {
  OutfitTryOnReview,
  createVisualReviewSession,
  createVisualReviewSessionController,
  visualReviewSelectionKey,
  visualReviewStatusKey,
} from "@/components/agents/outfit/OutfitTryOnReview";
import type {
  OutfitCapability,
  OutfitUsageToday,
  VisualReviewResult,
  VisualReviewTrigger,
} from "@/api";
import type {
  OutfitRecommendationSnapshot,
  OutfitWardrobe,
} from "@/api/outfit";

const READY_CAPABILITY: OutfitCapability = {
  enabled: true,
  primaryPersonConfigured: true,
  storageReady: true,
  voiceIngressConfigured: false,
  cameraAllowlisted: true,
  lastProviderStatus: "last_success",
};

const COMPLETE_USAGE: OutfitUsageToday = {
  date: "2026-08-22",
  timezone: "Asia/Shanghai",
  callCount: 2,
  inputTokens: 13,
  outputTokens: 5,
  estimatedTotalTokens: 21,
  complete: true,
};

const WARDROBE: OutfitWardrobe = {
  pendingDrafts: [
    {
      draftId: "draft-private",
      name: "Navy shirt",
      category: "top",
      sourceTypes: ["photo"],
      status: "pending",
    },
  ],
  availableItems: [
    {
      itemId: "item-private",
      name: "Black trousers",
      category: "bottom",
      sourceTypes: ["manual"],
      status: "confirmed",
      availability: "available",
    },
  ],
};

const RECOMMENDATION_WARDROBE: OutfitWardrobe = {
  pendingDrafts: [],
  availableItems: [
    { itemId: "item-top", name: "Navy shirt", category: "top", sourceTypes: ["manual"], status: "confirmed", availability: "available" },
    { itemId: "item-bottom", name: "Gray trousers", category: "bottom", sourceTypes: ["manual"], status: "confirmed", availability: "available" },
    { itemId: "item-shoes", name: "White shoes", category: "shoes", sourceTypes: ["manual"], status: "confirmed", availability: "available" },
    { itemId: "item-dress", name: "Black dress", category: "dress", sourceTypes: ["manual"], status: "confirmed", availability: "available" },
  ],
};

const READY_RECOMMENDATION: OutfitRecommendationSnapshot = {
  snapshotId: "rec-private",
  context: { occasion: null, activity: "commute", dayKind: "unknown" },
  status: "ready",
  optionItemIds: [
    ["item-top", "item-bottom", "item-shoes"],
    ["item-dress", "item-shoes"],
  ],
  rankingVersion: "private-ranking",
  createdAtMs: 321,
};

const REVIEW_TRIGGER: VisualReviewTrigger = {
  triggerId: "trigger-private",
  recommendationId: "recommendation-private",
  deviceId: "camera-private",
};

const NEXT_REVIEW_TRIGGER: VisualReviewTrigger = {
  triggerId: "trigger-next",
  recommendationId: "recommendation-next",
  deviceId: "camera-next",
};

const COMPLETED_REVIEW: VisualReviewResult = {
  status: "completed",
  errorCode: null,
};

const tryOnReviewPath = fileURLToPath(
  new URL("../src/components/agents/outfit/OutfitTryOnReview.tsx", import.meta.url),
);

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function renderReady(
  view: OutfitPanelView,
  usage = COMPLETE_USAGE,
  wardrobe: OutfitPanelLoadState<OutfitWardrobe> = {
    data: WARDROBE,
    loading: false,
    error: undefined,
  },
  recommendation: OutfitPanelLoadState<OutfitRecommendationSnapshot> = {
    data: undefined,
    loading: false,
    error: undefined,
  },
): string {
  return renderToStaticMarkup(
    <OutfitPanelReadyContent
      capability={READY_CAPABILITY}
      usage={usage}
      wardrobe={wardrobe}
      recommendation={recommendation}
      recommendationScenario="commute"
      activeView={view}
      onViewChange={() => {}}
      onWardrobeRetry={() => {}}
      onRecommendationScenarioChange={() => {}}
      onRecommendationRequest={() => {}}
    />,
  ).replaceAll("&#x27;", "'");
}

beforeAll(async () => {
  await i18n.changeLanguage("en");
});

afterAll(async () => {
  await i18n.changeLanguage("zh");
});

describe("OutfitPanel load state controller", () => {
  it("keeps loading until both independent reads settle", () => {
    expect(
      resolveOutfitPanelPhase({
        capability: { data: undefined, loading: false, error: undefined },
        usage: { data: undefined, loading: true, error: undefined },
      }),
    ).toEqual({ kind: "loading" });
  });

  it("drops stale content and exposes a targeted retry after a read error", () => {
    const phase = resolveOutfitPanelPhase({
      capability: { data: READY_CAPABILITY, loading: false, error: new Error("no") },
      usage: { data: COMPLETE_USAGE, loading: false, error: undefined },
    });

    expect(phase).toEqual({ kind: "error", retryTarget: "capability" });
    expect(phase).not.toHaveProperty("capability");
    expect(phase).not.toHaveProperty("usage");
  });

  it("exposes an initial read failure instead of waiting forever for data", () => {
    expect(
      resolveOutfitPanelPhase({
        capability: { data: undefined, loading: false, error: undefined },
        usage: { data: undefined, loading: false, error: new Error("no") },
      }),
    ).toEqual({ kind: "error", retryTarget: "usage" });
  });

  it("prioritizes a settled error over the other independent pending read", () => {
    expect(
      resolveOutfitPanelPhase({
        capability: { data: undefined, loading: false, error: new Error("no") },
        usage: { data: undefined, loading: true, error: undefined },
      }),
    ).toEqual({ kind: "error", retryTarget: "capability" });
  });
});

describe("OutfitPanel ready views", () => {
  it("renders an idle recommendation command without an automatic request", () => {
    const markup = renderReady("today");

    expect(markup).toContain("Today's recommendation");
    expect(markup).toContain("No recommendation has been generated");
    expect(markup).toContain("Scenario");
    expect(markup).toContain("Generate recommendation");
    expect(markup).toContain("<select");
    expect(markup).not.toContain("Provider status");
    expect(markup).not.toContain("recommendation-private");
  });

  it("renders recommendation loading and fixed error states", () => {
    const loading = renderReady("today", COMPLETE_USAGE, undefined, {
      data: undefined,
      loading: true,
      error: undefined,
    });
    const failed = renderReady("today", COMPLETE_USAGE, undefined, {
      data: undefined,
      loading: false,
      error: new Error("private weather city provider path"),
    });

    expect(loading).toContain("Generating recommendation");
    expect(failed).toContain("Recommendation is unavailable");
    expect(failed).toContain("Retry");
    expect(failed).not.toContain("private weather city provider path");
    expect(failed).not.toContain("Beijing");
  });

  it("renders ready options using wardrobe names without opaque identifiers", () => {
    const markup = renderReady(
      "today",
      COMPLETE_USAGE,
      { data: RECOMMENDATION_WARDROBE, loading: false, error: undefined },
      { data: READY_RECOMMENDATION, loading: false, error: undefined },
    );

    expect(markup).toContain("Option 1");
    expect(markup).toContain("Navy shirt");
    expect(markup).toContain("Gray trousers");
    expect(markup).toContain("White shoes");
    expect(markup).toContain("Black dress");
    expect(markup).not.toContain("rec-private");
    expect(markup).not.toContain("item-top");
    expect(markup).not.toContain("private-ranking");
  });

  it("renders insufficient inventory without inventing weather capabilities", () => {
    const markup = renderReady("today", COMPLETE_USAGE, undefined, {
      data: { ...READY_RECOMMENDATION, status: "insufficient_inventory", optionItemIds: [] },
      loading: false,
      error: undefined,
    });

    expect(markup).toContain("Not enough confirmed items match this scenario");
    expect(markup).not.toContain("waterproof");
  });

  it("hides a recommendation whose item IDs cannot be mapped to wardrobe names", () => {
    const markup = renderReady("today", COMPLETE_USAGE, {
      data: WARDROBE,
      loading: false,
      error: undefined,
    }, {
      data: READY_RECOMMENDATION,
      loading: false,
      error: undefined,
    });

    expect(markup).toContain("Recommendation is unavailable");
    expect(markup).not.toContain("item-top");
    expect(markup).not.toContain("rec-private");
  });

  it("fails closed when wardrobe names cannot be loaded", () => {
    const markup = renderReady(
      "today",
      COMPLETE_USAGE,
      { data: undefined, loading: false, error: new Error("private storage path") },
      { data: READY_RECOMMENDATION, loading: false, error: undefined },
    );

    expect(markup).toContain("Recommendation is unavailable");
    expect(markup).not.toContain("Matching wardrobe items");
    expect(markup).not.toContain("private storage path");
  });

  it("renders pending and available wardrobe facts without source references", () => {
    const markup = renderReady("wardrobe");

    expect(markup).toContain("My wardrobe");
    expect(markup).toContain("Storage ready");
    expect(markup).toContain("Pending confirmation");
    expect(markup).toContain("Available items");
    expect(markup).toContain("Navy shirt");
    expect(markup).toContain("Black trousers");
    expect(markup).not.toContain("draft-private");
    expect(markup).not.toContain("item-private");
    expect(markup).not.toContain("private-source");
  });

  it("keeps wardrobe errors local to the wardrobe view and exposes retry", () => {
    const markup = renderReady("wardrobe", COMPLETE_USAGE, {
      data: undefined,
      loading: false,
      error: new Error("private wardrobe failure"),
    });

    expect(markup).toContain("Wardrobe information is unavailable");
    expect(markup).toContain("Retry");
    expect(markup).not.toContain("private wardrobe failure");
  });

  it("keeps the empty wardrobe state honest when both lists are empty", () => {
    const markup = renderReady("wardrobe", COMPLETE_USAGE, {
      data: { pendingDrafts: [], availableItems: [] },
      loading: false,
      error: undefined,
    });

    expect(markup).toContain("No wardrobe items are available");
  });

  it("keeps try-on review non-executable when no selection is supplied", () => {
    const markup = renderReady("tryOn");

    expect(markup).toContain("Try-on review");
    expect(markup).toContain("No review selection is available");
    expect(markup).not.toContain("Request visual review");
    expect(markup).not.toContain("<input");
  });

  it("shows complete admin usage separately from the user-facing views", () => {
    const markup = renderReady("today");

    expect(markup).toContain("Administrative diagnostics");
    expect(markup).toContain("Input tokens");
    expect(markup).toContain("Estimated total tokens");
    expect(markup).toContain(">21<");
  });

  it("shows incomplete token usage as unknown rather than zero", () => {
    const markup = renderReady("today", {
      ...COMPLETE_USAGE,
      complete: false,
      inputTokens: null,
      outputTokens: null,
      estimatedTotalTokens: null,
    });

    expect(markup).toContain("Unknown");
    expect(markup).not.toContain(">0<");
  });
});

describe("OutfitTryOnReview", () => {
  it("mounts a complete-keyed local session without synchronizing a parent controller during render", () => {
    const source = readFileSync(tryOnReviewPath, "utf8");
    const parentStart = source.indexOf("export function OutfitTryOnReview");
    const sessionStart = source.indexOf("function OutfitTryOnReviewSession");
    const parent = source.slice(parentStart, sessionStart);
    const session = source.slice(sessionStart);

    expect(parentStart).toBeGreaterThanOrEqual(0);
    expect(sessionStart).toBeGreaterThan(parentStart);
    expect(parent).toContain("<OutfitTryOnReviewSession");
    expect(parent).toContain("key={visualReviewSelectionKey(trigger)}");
    expect(parent).not.toContain("synchronize(trigger)");
    expect(parent).not.toContain("createVisualReviewSessionController");
    expect(session).toContain("useState(() => createVisualReviewSession(trigger))");
    expect(session).toContain("controller.synchronize(undefined)");
  });

  it("keeps committed A local session current when an abandoned B session is initialized", async () => {
    const gate = deferred<VisualReviewResult>();
    const request = vi.fn(() => gate.promise);
    const committedA = createVisualReviewSession(REVIEW_TRIGGER, request);
    const runA = committedA.begin();
    const abandonedB = createVisualReviewSession(NEXT_REVIEW_TRIGGER, request);

    expect(committedA.current().key).toBe(visualReviewSelectionKey(REVIEW_TRIGGER));
    expect(abandonedB.current().key).toBe(
      visualReviewSelectionKey(NEXT_REVIEW_TRIGGER),
    );

    gate.resolve(COMPLETED_REVIEW);

    await expect(runA?.completion).resolves.toMatchObject({ kind: "result" });
    expect(committedA.isCurrent(runA!.ticket)).toBe(true);
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("does not render identifiers while a real selection only enables one request command", () => {
    const markup = renderToStaticMarkup(<OutfitTryOnReview trigger={REVIEW_TRIGGER} />);

    expect(markup).toContain("Request visual review");
    expect(markup).not.toContain(REVIEW_TRIGGER.triggerId);
    expect(markup).not.toContain(REVIEW_TRIGGER.recommendationId);
    expect(markup).not.toContain(REVIEW_TRIGGER.deviceId);
  });

  it.each([
    ["trigger ID", { ...REVIEW_TRIGGER, triggerId: "trigger-other" }],
    ["recommendation ID", { ...REVIEW_TRIGGER, recommendationId: "recommendation-other" }],
    ["device ID", { ...REVIEW_TRIGGER, deviceId: "camera-other" }],
  ] as const)("creates a fresh selection when the %s changes", async (_label, next) => {
    const request = vi.fn(async () => COMPLETED_REVIEW);
    const session = createVisualReviewSessionController(request);
    const first = session.synchronize(REVIEW_TRIGGER);
    const runA = session.begin();
    const second = session.synchronize(next);
    const run = session.begin();

    expect(second.key).not.toBe(first.key);
    expect(second.generation).toBeGreaterThan(first.generation);
    expect(run?.ticket.trigger).toEqual(next);
    await expect(runA?.completion).resolves.toMatchObject({ kind: "stale" });
    await expect(run?.completion).resolves.toMatchObject({ kind: "result" });
    expect(request).toHaveBeenCalledTimes(2);
    expect(request).toHaveBeenNthCalledWith(1, REVIEW_TRIGGER);
    expect(request).toHaveBeenNthCalledWith(2, next);
  });

  it("allows exactly one request for one stable selection", async () => {
    const gate = deferred<VisualReviewResult>();
    const request = vi.fn(() => gate.promise);
    const session = createVisualReviewSessionController(request);

    const first = session.synchronize(REVIEW_TRIGGER);
    const run = session.begin();
    const sameSelection = session.synchronize({ ...REVIEW_TRIGGER });

    expect(sameSelection).toEqual(first);
    expect(session.begin()).toBeUndefined();
    expect(request).toHaveBeenCalledTimes(1);

    gate.resolve(COMPLETED_REVIEW);
    await expect(run?.completion).resolves.toMatchObject({ kind: "result" });
  });

  it("marks A's deferred result stale after switching to B", async () => {
    const gate = deferred<VisualReviewResult>();
    const request = vi.fn(() => gate.promise);
    const session = createVisualReviewSessionController(request);

    session.synchronize(REVIEW_TRIGGER);
    const runA = session.begin();
    const selectionB = session.synchronize(NEXT_REVIEW_TRIGGER);

    gate.resolve(COMPLETED_REVIEW);

    await expect(runA?.completion).resolves.toMatchObject({ kind: "stale" });
    expect(session.current()).toEqual(selectionB);
    expect(session.begin()?.ticket.trigger).toEqual(NEXT_REVIEW_TRIGGER);
  });

  it("marks A's deferred rejection stale after clearing the selection", async () => {
    const gate = deferred<VisualReviewResult>();
    const request = vi.fn(() => gate.promise);
    const session = createVisualReviewSessionController(request);

    session.synchronize(REVIEW_TRIGGER);
    const runA = session.begin();
    const emptySelection = session.synchronize(undefined);

    gate.reject(new Error("request failed"));

    await expect(runA?.completion).resolves.toMatchObject({ kind: "stale" });
    expect(session.current()).toEqual(emptySelection);
    expect(emptySelection.key).toBeUndefined();
    expect(session.begin()).toBeUndefined();
  });

  it("marks A's deferred rejection stale after switching to B", async () => {
    const gate = deferred<VisualReviewResult>();
    const request = vi.fn(() => gate.promise);
    const session = createVisualReviewSessionController(request);

    session.synchronize(REVIEW_TRIGGER);
    const runA = session.begin();
    const selectionB = session.synchronize(NEXT_REVIEW_TRIGGER);

    gate.reject(new Error("request failed"));

    await expect(runA?.completion).resolves.toMatchObject({ kind: "stale" });
    expect(session.current()).toEqual(selectionB);
  });

  it("marks A's deferred result stale after clearing the selection", async () => {
    const gate = deferred<VisualReviewResult>();
    const request = vi.fn(() => gate.promise);
    const session = createVisualReviewSessionController(request);

    session.synchronize(REVIEW_TRIGGER);
    const runA = session.begin();
    const emptySelection = session.synchronize(undefined);

    gate.resolve(COMPLETED_REVIEW);

    await expect(runA?.completion).resolves.toMatchObject({ kind: "stale" });
    expect(session.current()).toEqual(emptySelection);
    expect(emptySelection.key).toBeUndefined();
  });

  it.each([
    "evaluating",
    "completed",
    "rejected",
    "capture_failed",
    "provider_failed",
    "cleanup_failed",
  ] as const)("maps %s to an explicit localized review status", (status) => {
    expect(visualReviewStatusKey(status)).toBe(`agents.outfit.review.status.${status}`);
  });
});
