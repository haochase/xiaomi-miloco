import { afterEach, describe, expect, it, vi } from "vitest";
import {
  confirmOutfitWardrobeDraft,
  confirmOutfitRecommendedWear,
  confirmOutfitMomentTag,
  createOutfitWardrobeDraft,
  deleteOutfitWardrobeItem,
  deleteOutfitMedia,
  editOutfitMomentTag,
  getOutfitCapabilities,
  getOutfitMoment,
  listOutfitWardrobe,
  listOutfitWardrobeDrafts,
  listOutfitMoments,
  outfitMediaUrl,
  requestOutfitRecommendation,
  refreshOutfitMomentTags,
  rejectOutfitMomentTag,
  updateOutfitWardrobeItem,
} from "@/api/outfit";

const originalFetch = globalThis.fetch;

afterEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = originalFetch;
});

function mockNormalResponse(data: unknown): void {
  globalThis.fetch = vi.fn(async () =>
    new Response(JSON.stringify({ code: 0, message: "ok", data }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  ) as unknown as typeof fetch;
}

describe("Outfit moment API mapping", () => {
  it("maps a configured-owner snake_case moment list", async () => {
    mockNormalResponse([
      {
        moment_id: "moment-1",
        occurred_at_ms: 1000,
        timezone: "Asia/Shanghai",
        recommendation_id: "rec-1",
        confirmed_wear_event_id: "wear-1",
        item_ids: ["top-1", "bottom-1", "shoes-1"],
        source_event_ids: ["wear-1"],
        user_note: "rainy commute",
        created_at_ms: 1100,
        projection_version: 1,
        media_asset_ids: ["asset-1"],
        tags: [
          {
            tag_id: "tag-confirmed",
            moment_id: "moment-1",
            tag_type: "repeat_favorite",
            label: "A familiar favorite",
            narrative: "You chose a known combination.",
            evidence_signal_ids: ["signal-1"],
            source: "rule",
            confidence: 0.9,
            review_status: "confirmed",
            dedupe_key: "repeat:moment-1",
            generator_version: "rule-v1",
          },
        ],
      },
    ]);

    await expect(listOutfitMoments({ limit: 10 })).resolves.toEqual([
      expect.objectContaining({
        id: "moment-1",
        occurredAt: 1000,
        itemIds: ["top-1", "bottom-1", "shoes-1"],
        mediaAssetIds: ["asset-1"],
        confirmedTags: [expect.objectContaining({ id: "tag-confirmed" })],
        pendingTags: [],
      }),
    ]);

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/outfit/moments?limit=10",
      expect.anything(),
    );
  });

  it("rejects missing required source fields instead of fabricating a moment", async () => {
    mockNormalResponse([{ moment_id: "moment-1" }]);

    await expect(listOutfitMoments({ limit: 10 })).rejects.toEqual(
      expect.objectContaining({ status: 200 }),
    );
  });

  it("maps a detail response and constructs configured-owner private media URLs", async () => {
    mockNormalResponse({
      moment_id: "moment/1",
      occurred_at_ms: 1000,
      timezone: "Asia/Shanghai",
      recommendation_id: "rec-1",
      confirmed_wear_event_id: "wear-1",
      item_ids: ["top-1"],
      source_event_ids: ["wear-1"],
      created_at_ms: 1100,
      projection_version: 1,
    });

    await expect(getOutfitMoment("moment/1")).resolves.toMatchObject({
      id: "moment/1",
      mediaAssetIds: [],
      confirmedTags: [],
      pendingTags: [],
    });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/outfit/moments/moment%2F1",
      expect.anything(),
    );
    expect(outfitMediaUrl("asset/1", true)).toBe("/api/outfit/media/asset%2F1?download=true");
  });

  it("sends only explicit review actions for an existing tag key", async () => {
    mockNormalResponse([
      {
        tag_id: "tag-1",
        moment_id: "moment-1",
        tag_type: "repeat_favorite",
        label: "A familiar favorite",
        narrative: "You chose a known combination.",
        evidence_signal_ids: ["signal-1"],
        source: "rule",
        confidence: 0.9,
        review_status: "pending",
        dedupe_key: "repeat:moment-1",
        generator_version: "rule-v1",
      },
    ]);

    await expect(refreshOutfitMomentTags("moment-1")).resolves.toEqual([
      expect.objectContaining({ id: "tag-1" }),
    ]);
    expect(globalThis.fetch).toHaveBeenLastCalledWith(
      "/api/outfit/moments/moment-1/tags/refresh",
      expect.objectContaining({ method: "POST" }),
    );

    mockNormalResponse({
      tag_id: "tag-1",
      moment_id: "moment-1",
      tag_type: "repeat_favorite",
      label: "A familiar favorite",
      narrative: "You chose a known combination.",
      evidence_signal_ids: ["signal-1"],
      source: "rule",
      confidence: 0.9,
      review_status: "confirmed",
      dedupe_key: "repeat:moment-1",
      generator_version: "rule-v1",
    });
    await expect(confirmOutfitMomentTag("moment-1", "tag-1")).resolves.toMatchObject({
      reviewStatus: "confirmed",
    });
    await expect(rejectOutfitMomentTag("moment-1", "tag-1")).resolves.toMatchObject({
      reviewStatus: "confirmed",
    });
    await expect(
      editOutfitMomentTag("moment-1", "tag-1", {
        narrative: "A user-approved summary.",
      }),
    ).resolves.toMatchObject({ reviewStatus: "confirmed" });
  });

  it("maps an installed capability and treats only a missing optional route as absent", async () => {
    mockNormalResponse([{ id: "outfit_v2", enabled: true, api_version: "v1" }]);

    await expect(getOutfitCapabilities()).resolves.toEqual([
      { id: "outfit_v2", enabled: true, api_version: "v1" },
    ]);
    expect(globalThis.fetch).toHaveBeenLastCalledWith(
      "/api/outfit/capabilities",
      expect.anything(),
    );

    globalThis.fetch = vi.fn(async () => new Response("missing", { status: 404 })) as unknown as typeof fetch;
    await expect(getOutfitCapabilities()).resolves.toEqual([]);
  });

  it("deletes private media only through the explicit confirmed endpoint", async () => {
    mockNormalResponse({ deleted: true });

    await expect(deleteOutfitMedia("asset/1")).resolves.toBeUndefined();

    expect(globalThis.fetch).toHaveBeenLastCalledWith(
      "/api/outfit/media/asset%2F1?confirmed=true",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("maps an ownerless wardrobe lifecycle through explicit confirmation endpoints", async () => {
    mockNormalResponse([
      {
        item_id: "item-1",
        name: "navy cotton shirt",
        category: "top",
        source_type: "manual",
        source_reference: "closet shelf A",
        confirmed_at_ms: 1_000,
      },
    ]);

    await expect(listOutfitWardrobe()).resolves.toEqual([
      expect.objectContaining({
        id: "item-1",
        category: "top",
        sourceType: "manual",
      }),
    ]);
    expect(globalThis.fetch).toHaveBeenLastCalledWith(
      "/api/outfit/wardrobe",
      expect.anything(),
    );

    mockNormalResponse([
      {
        draft_id: "draft-1",
        name: "navy cotton shirt",
        category: "top",
        source_type: "manual",
        source_reference: "closet shelf A",
        created_at_ms: 900,
        status: "pending",
      },
    ]);
    await expect(listOutfitWardrobeDrafts()).resolves.toEqual([
      expect.objectContaining({ id: "draft-1", status: "pending" }),
    ]);

    mockNormalResponse({
      draft_id: "draft-1",
      name: "navy cotton shirt",
      category: "top",
      source_type: "manual",
      source_reference: "closet shelf A",
      created_at_ms: 900,
      status: "pending",
    });
    await expect(
      createOutfitWardrobeDraft({
        name: "navy cotton shirt",
        category: "top",
        sourceType: "manual",
        sourceReference: "closet shelf A",
      }),
    ).resolves.toMatchObject({ id: "draft-1" });
    expect(globalThis.fetch).toHaveBeenLastCalledWith(
      "/api/outfit/wardrobe/drafts",
      expect.objectContaining({ method: "POST" }),
    );

    mockNormalResponse({
      item_id: "item-1",
      name: "navy cotton shirt",
      category: "top",
      source_type: "manual",
      source_reference: "closet shelf A",
      confirmed_at_ms: 1_000,
    });
    await expect(confirmOutfitWardrobeDraft("draft-1")).resolves.toMatchObject({
      id: "item-1",
    });

    mockNormalResponse({
      item_id: "item-1",
      name: "navy linen shirt",
      category: "outerwear",
      source_type: "manual",
      source_reference: "closet shelf A",
      confirmed_at_ms: 1_000,
    });
    await expect(
      updateOutfitWardrobeItem("item-1", {
        name: "navy linen shirt",
        category: "outerwear",
      }),
    ).resolves.toMatchObject({ name: "navy linen shirt" });

    mockNormalResponse({ deleted: true });
    await expect(deleteOutfitWardrobeItem("item-1")).resolves.toBeUndefined();
    expect(globalThis.fetch).toHaveBeenLastCalledWith(
      "/api/outfit/wardrobe/item-1?confirmed=true",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("maps scenario-gated inventory recommendations and sends explicit wear confirmation", async () => {
    mockNormalResponse({
      status: "needs_context",
      recommendation_id: null,
      options: [],
      missing_context: ["occasion_or_activity"],
      inventory_hints: [],
    });

    await expect(requestOutfitRecommendation({})).resolves.toEqual({
      status: "needs_context",
      recommendationId: undefined,
      options: [],
      missingContext: ["occasion_or_activity"],
      inventoryHints: [],
    });
    expect(globalThis.fetch).toHaveBeenLastCalledWith(
      "/api/outfit/recommendations",
      expect.objectContaining({ method: "POST", body: "{}" }),
    );

    mockNormalResponse({
      status: "ready",
      recommendation_id: "recommendation-1",
      options: [
        {
          option_id: "option-1",
          item_ids: ["top-1", "bottom-1", "shoes-1"],
          composition_type: "top_bottom_shoes",
        },
      ],
      missing_context: [],
      inventory_hints: [],
    });
    await expect(
      requestOutfitRecommendation({ occasion: "team meeting" }),
    ).resolves.toMatchObject({
      status: "ready",
      recommendationId: "recommendation-1",
      options: [
        { id: "option-1", itemIds: ["top-1", "bottom-1", "shoes-1"] },
      ],
    });

    mockNormalResponse({
      event_id: "wear-1",
      moment_id: "moment-wear-1",
      recommendation_id: "recommendation-1",
      item_ids: ["top-1", "bottom-1", "shoes-1"],
      moment: {
        moment_id: "moment-wear-1",
        occurred_at_ms: 1000,
        timezone: "Asia/Shanghai",
        recommendation_id: "recommendation-1",
        confirmed_wear_event_id: "wear-1",
        item_ids: ["top-1", "bottom-1", "shoes-1"],
        source_event_ids: ["wear-1"],
        created_at_ms: 1100,
        projection_version: 1,
      },
    });
    await expect(
      confirmOutfitRecommendedWear({
        recommendationId: "recommendation-1",
        optionId: "option-1",
        confirmationId: "team-meeting-20260812",
      }),
    ).resolves.toMatchObject({
      eventId: "wear-1",
      momentId: "moment-wear-1",
    });
    expect(globalThis.fetch).toHaveBeenLastCalledWith(
      "/api/outfit/wear-confirmations",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          recommendation_id: "recommendation-1",
          option_id: "option-1",
          confirmation_id: "team-meeting-20260812",
          timezone: "Asia/Shanghai",
          confirmed: true,
        }),
      }),
    );
  });
});
