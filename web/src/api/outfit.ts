import { ApiError, apiFetch } from "./client";
import type {
  OutfitMoment,
  OutfitMomentTag,
  OutfitRecommendation,
  OutfitRecommendationOption,
  OutfitWardrobeCategory,
  OutfitWardrobeDraft,
  OutfitWardrobeItem,
  OutfitWardrobeSourceType,
  OutfitWearConfirmation,
} from "@/lib/types";

interface Normal<T> {
  code: number;
  message: string;
  data: T;
}

export interface OutfitCapability {
  id: string;
  enabled: boolean;
  api_version: string;
}

export interface OutfitMomentQuery {
  limit: 10 | 30;
  sinceMs?: number;
}

export interface CreateOutfitWardrobeDraftInput {
  name: string;
  category: OutfitWardrobeCategory;
  sourceType: OutfitWardrobeSourceType;
  sourceReference: string;
}

export interface UpdateOutfitWardrobeItemInput {
  name?: string;
  category?: OutfitWardrobeCategory;
}

export interface OutfitRecommendationInput {
  occasion?: string;
  activity?: string;
  dayKind?: "workday" | "rest_day";
  weatherSummary?: string;
}

export interface ConfirmOutfitRecommendedWearInput {
  recommendationId: string;
  optionId: string;
  confirmationId: string;
  timezone?: string;
}

export async function listOutfitMoments(
  query: OutfitMomentQuery,
): Promise<OutfitMoment[]> {
  const params = new URLSearchParams({ limit: String(query.limit) });
  if (query.sinceMs !== undefined) {
    params.set("since_ms", String(query.sinceMs));
  }
  const response = await apiFetch<Normal<unknown>>(
    `/api/outfit/moments?${params.toString()}`,
  );
  return unpackMomentList(response.data).map(mapMoment);
}

export async function getOutfitMoment(momentId: string): Promise<OutfitMoment> {
  const response = await apiFetch<Normal<unknown>>(
    `/api/outfit/moments/${encodeURIComponent(momentId)}`,
  );
  return mapMoment(response.data);
}

export async function refreshOutfitMomentTags(
  momentId: string,
): Promise<OutfitMomentTag[]> {
  const response = await apiFetch<Normal<unknown>>(
    `/api/outfit/moments/${encodeURIComponent(momentId)}/tags/refresh`,
    {
      method: "POST",
    },
  );
  return requiredArray(response.data, "tag refresh response").map(mapTag);
}

export async function confirmOutfitMomentTag(
  momentId: string,
  tagId: string,
): Promise<OutfitMomentTag> {
  return reviewOutfitMomentTag(momentId, tagId, "confirm");
}

export async function rejectOutfitMomentTag(
  momentId: string,
  tagId: string,
): Promise<OutfitMomentTag> {
  return reviewOutfitMomentTag(momentId, tagId, "reject");
}

export async function editOutfitMomentTag(
  momentId: string,
  tagId: string,
  patch: { label?: string; narrative?: string },
): Promise<OutfitMomentTag> {
  const response = await apiFetch<Normal<unknown>>(
    `/api/outfit/moments/${encodeURIComponent(momentId)}/tags/${encodeURIComponent(tagId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        ...(patch.label !== undefined ? { label: patch.label } : {}),
        ...(patch.narrative !== undefined ? { narrative: patch.narrative } : {}),
      }),
    },
  );
  return mapTag(response.data);
}

export function outfitMediaUrl(
  assetId: string,
  download = false,
): string {
  const query = new URLSearchParams();
  if (download) {
    query.set("download", "true");
  }
  const suffix = query.toString();
  return `/api/outfit/media/${encodeURIComponent(assetId)}${suffix ? `?${suffix}` : ""}`;
}

export async function deleteOutfitMedia(assetId: string): Promise<void> {
  const response = await apiFetch<Normal<unknown>>(
    `/api/outfit/media/${encodeURIComponent(assetId)}?confirmed=true`,
    { method: "DELETE" },
  );
  if (!isRecord(response.data) || response.data.deleted !== true) {
    throw malformedResponse("media delete response must confirm deletion");
  }
}

export async function listOutfitWardrobe(): Promise<OutfitWardrobeItem[]> {
  const response = await apiFetch<Normal<unknown>>("/api/outfit/wardrobe");
  return requiredArray(response.data, "wardrobe list response").map(mapWardrobeItem);
}

export async function listOutfitWardrobeDrafts(): Promise<OutfitWardrobeDraft[]> {
  const response = await apiFetch<Normal<unknown>>("/api/outfit/wardrobe/drafts");
  return requiredArray(response.data, "wardrobe draft list response").map(mapWardrobeDraft);
}

export async function createOutfitWardrobeDraft(
  input: CreateOutfitWardrobeDraftInput,
): Promise<OutfitWardrobeDraft> {
  const response = await apiFetch<Normal<unknown>>("/api/outfit/wardrobe/drafts", {
    method: "POST",
    body: JSON.stringify({
      name: input.name,
      category: input.category,
      source_type: input.sourceType,
      source_reference: input.sourceReference,
    }),
  });
  return mapWardrobeDraft(response.data);
}

export async function confirmOutfitWardrobeDraft(
  draftId: string,
): Promise<OutfitWardrobeItem> {
  const response = await apiFetch<Normal<unknown>>(
    `/api/outfit/wardrobe/drafts/${encodeURIComponent(draftId)}/confirm`,
    {
      method: "POST",
      body: JSON.stringify({ confirmed: true }),
    },
  );
  return mapWardrobeItem(response.data);
}

export async function discardOutfitWardrobeDraft(draftId: string): Promise<void> {
  await requireDeletion(
    `/api/outfit/wardrobe/drafts/${encodeURIComponent(draftId)}?confirmed=true`,
  );
}

export async function updateOutfitWardrobeItem(
  itemId: string,
  input: UpdateOutfitWardrobeItemInput,
): Promise<OutfitWardrobeItem> {
  const response = await apiFetch<Normal<unknown>>(
    `/api/outfit/wardrobe/${encodeURIComponent(itemId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        ...(input.name !== undefined ? { name: input.name } : {}),
        ...(input.category !== undefined ? { category: input.category } : {}),
      }),
    },
  );
  return mapWardrobeItem(response.data);
}

export async function deleteOutfitWardrobeItem(itemId: string): Promise<void> {
  await requireDeletion(`/api/outfit/wardrobe/${encodeURIComponent(itemId)}?confirmed=true`);
}

export async function requestOutfitRecommendation(
  input: OutfitRecommendationInput,
): Promise<OutfitRecommendation> {
  const response = await apiFetch<Normal<unknown>>("/api/outfit/recommendations", {
    method: "POST",
    body: JSON.stringify({
      ...(input.occasion !== undefined ? { occasion: input.occasion } : {}),
      ...(input.activity !== undefined ? { activity: input.activity } : {}),
      ...(input.dayKind !== undefined ? { day_kind: input.dayKind } : {}),
      ...(input.weatherSummary !== undefined
        ? { weather_summary: input.weatherSummary }
        : {}),
    }),
  });
  return mapRecommendation(response.data);
}

export async function confirmOutfitRecommendedWear(
  input: ConfirmOutfitRecommendedWearInput,
): Promise<OutfitWearConfirmation> {
  const response = await apiFetch<Normal<unknown>>(
    "/api/outfit/wear-confirmations",
    {
      method: "POST",
      body: JSON.stringify({
        recommendation_id: input.recommendationId,
        option_id: input.optionId,
        confirmation_id: input.confirmationId,
        timezone: input.timezone ?? "Asia/Shanghai",
        confirmed: true,
      }),
    },
  );
  return mapWearConfirmation(response.data);
}

export async function getOutfitCapabilities(): Promise<OutfitCapability[]> {
  try {
    const response = await apiFetch<Normal<unknown>>("/api/outfit/capabilities");
    return mapCapabilities(response.data);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return [];
    }
    throw error;
  }
}

function unpackMomentList(data: unknown): unknown[] {
  if (Array.isArray(data)) {
    return data;
  }
  if (isRecord(data) && Array.isArray(data.moments)) {
    return data.moments;
  }
  throw malformedResponse("moment list must be an array");
}

function requiredArray(data: unknown, name: string): unknown[] {
  if (!Array.isArray(data)) {
    throw malformedResponse(`${name} must be an array`);
  }
  return data;
}

async function reviewOutfitMomentTag(
  momentId: string,
  tagId: string,
  action: "confirm" | "reject",
): Promise<OutfitMomentTag> {
  const response = await apiFetch<Normal<unknown>>(
    `/api/outfit/moments/${encodeURIComponent(momentId)}/tags/${encodeURIComponent(tagId)}/${action}`,
    {
      method: "POST",
    },
  );
  return mapTag(response.data);
}

function mapCapabilities(value: unknown): OutfitCapability[] {
  if (!Array.isArray(value)) {
    throw malformedResponse("capabilities must be an array");
  }
  return value.map((capability) => {
    if (!isRecord(capability)) {
      throw malformedResponse("capability must be an object");
    }
    const id = requiredString(capability.id, "capability.id");
    if (typeof capability.enabled !== "boolean") {
      throw malformedResponse("capability.enabled must be a boolean");
    }
    return {
      id,
      enabled: capability.enabled,
      api_version: requiredString(capability.api_version, "capability.api_version"),
    };
  });
}

function mapMoment(value: unknown): OutfitMoment {
  if (!isRecord(value)) {
    throw malformedResponse("moment must be an object");
  }
  const tags = optionalArray(value.tags, "tags").map(mapTag);
  return {
    id: requiredString(value.moment_id, "moment_id"),
    occurredAt: requiredNumber(value.occurred_at_ms, "occurred_at_ms"),
    timezone: requiredString(value.timezone, "timezone"),
    recommendationId: requiredString(value.recommendation_id, "recommendation_id"),
    confirmedWearEventId: requiredString(
      value.confirmed_wear_event_id,
      "confirmed_wear_event_id",
    ),
    itemIds: requiredStringArray(value.item_ids, "item_ids"),
    sourceEventIds: requiredStringArray(value.source_event_ids, "source_event_ids"),
    mediaAssetIds: optionalStringArray(value.media_asset_ids, "media_asset_ids"),
    confirmedTags: tags.filter(
      (tag) => tag.reviewStatus === "confirmed" || tag.reviewStatus === "edited",
    ),
    pendingTags: tags.filter((tag) => tag.reviewStatus === "pending"),
    userNote: optionalString(value.user_note, "user_note"),
    createdAt: requiredNumber(value.created_at_ms, "created_at_ms"),
    projectionVersion: requiredNumber(value.projection_version, "projection_version"),
  };
}

function mapWardrobeDraft(value: unknown): OutfitWardrobeDraft {
  if (!isRecord(value)) {
    throw malformedResponse("wardrobe draft must be an object");
  }
  const status = requiredString(value.status, "wardrobe draft.status");
  if (status !== "pending") {
    throw malformedResponse("wardrobe draft.status is unsupported");
  }
  return {
    id: requiredString(value.draft_id, "wardrobe draft.draft_id"),
    name: requiredString(value.name, "wardrobe draft.name"),
    category: mapWardrobeCategory(value.category, "wardrobe draft.category"),
    sourceType: mapWardrobeSourceType(value.source_type, "wardrobe draft.source_type"),
    sourceReference: requiredString(
      value.source_reference,
      "wardrobe draft.source_reference",
    ),
    createdAt: requiredNumber(value.created_at_ms, "wardrobe draft.created_at_ms"),
    status,
  };
}

function mapWardrobeItem(value: unknown): OutfitWardrobeItem {
  if (!isRecord(value)) {
    throw malformedResponse("wardrobe item must be an object");
  }
  return {
    id: requiredString(value.item_id, "wardrobe item.item_id"),
    name: requiredString(value.name, "wardrobe item.name"),
    category: mapWardrobeCategory(value.category, "wardrobe item.category"),
    sourceType: mapWardrobeSourceType(value.source_type, "wardrobe item.source_type"),
    sourceReference: requiredString(
      value.source_reference,
      "wardrobe item.source_reference",
    ),
    confirmedAt: requiredNumber(value.confirmed_at_ms, "wardrobe item.confirmed_at_ms"),
  };
}

function mapRecommendation(value: unknown): OutfitRecommendation {
  if (!isRecord(value)) {
    throw malformedResponse("recommendation must be an object");
  }
  const status = requiredString(value.status, "recommendation.status");
  if (
    status !== "needs_context" &&
    status !== "ready" &&
    status !== "insufficient_inventory"
  ) {
    throw malformedResponse("recommendation.status is unsupported");
  }
  const recommendationId = optionalString(
    value.recommendation_id,
    "recommendation.recommendation_id",
  );
  const options = optionalArray(value.options, "recommendation.options").map(
    mapRecommendationOption,
  );
  const missingContext = optionalStringArray(
    value.missing_context,
    "recommendation.missing_context",
  );
  const inventoryHints = optionalStringArray(
    value.inventory_hints,
    "recommendation.inventory_hints",
  );
  if (status === "needs_context") {
    if (recommendationId || options.length || !missingContext.length) {
      throw malformedResponse("context request has an invalid recommendation state");
    }
  } else if ((recommendationId === undefined) !== (options.length === 0)) {
    throw malformedResponse("recommendation snapshot and options must agree");
  }
  return {
    status,
    recommendationId,
    options,
    missingContext,
    inventoryHints,
  };
}

function mapRecommendationOption(value: unknown): OutfitRecommendationOption {
  if (!isRecord(value)) {
    throw malformedResponse("recommendation option must be an object");
  }
  const compositionType = requiredString(
    value.composition_type,
    "recommendation option.composition_type",
  );
  if (compositionType !== "top_bottom_shoes" && compositionType !== "dress_shoes") {
    throw malformedResponse("recommendation option.composition_type is unsupported");
  }
  return {
    id: requiredString(value.option_id, "recommendation option.option_id"),
    itemIds: requiredStringArray(value.item_ids, "recommendation option.item_ids"),
    compositionType,
  };
}

function mapWearConfirmation(value: unknown): OutfitWearConfirmation {
  if (!isRecord(value)) {
    throw malformedResponse("wear confirmation must be an object");
  }
  return {
    eventId: requiredString(value.event_id, "wear confirmation.event_id"),
    momentId: requiredString(value.moment_id, "wear confirmation.moment_id"),
    recommendationId: requiredString(
      value.recommendation_id,
      "wear confirmation.recommendation_id",
    ),
    itemIds: requiredStringArray(value.item_ids, "wear confirmation.item_ids"),
    moment: mapMoment(value.moment),
  };
}

function mapTag(value: unknown): OutfitMomentTag {
  if (!isRecord(value)) {
    throw malformedResponse("tag must be an object");
  }
  const reviewStatus = requiredString(value.review_status, "tag.review_status");
  if (!isReviewStatus(reviewStatus)) {
    throw malformedResponse("tag.review_status is unsupported");
  }
  const source = requiredString(value.source, "tag.source");
  if (source !== "rule" && source !== "model" && source !== "user") {
    throw malformedResponse("tag.source is unsupported");
  }
  return {
    id: requiredString(value.tag_id, "tag_id"),
    momentId: requiredString(value.moment_id, "tag.moment_id"),
    type: requiredString(value.tag_type, "tag_type"),
    label: requiredString(value.label, "tag.label"),
    narrative: requiredString(value.narrative, "tag.narrative"),
    evidenceSignalIds: requiredStringArray(
      value.evidence_signal_ids,
      "tag.evidence_signal_ids",
    ),
    source,
    confidence: requiredNumber(value.confidence, "tag.confidence"),
    reviewStatus,
    dedupeKey: requiredString(value.dedupe_key, "tag.dedupe_key"),
    generatorVersion: requiredString(value.generator_version, "tag.generator_version"),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw malformedResponse(`${name} must be a non-empty string`);
  }
  return value;
}

function optionalString(value: unknown, name: string): string | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  return requiredString(value, name);
}

function requiredNumber(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw malformedResponse(`${name} must be a finite number`);
  }
  return value;
}

function optionalArray(value: unknown, name: string): unknown[] {
  if (value === undefined) {
    return [];
  }
  if (!Array.isArray(value)) {
    throw malformedResponse(`${name} must be an array`);
  }
  return value;
}

function requiredStringArray(value: unknown, name: string): string[] {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string" || !entry.trim())) {
    throw malformedResponse(`${name} must be a non-empty string array`);
  }
  return [...value];
}

function optionalStringArray(value: unknown, name: string): string[] {
  if (value === undefined) {
    return [];
  }
  return requiredStringArray(value, name);
}

function isReviewStatus(value: string): value is OutfitMomentTag["reviewStatus"] {
  return ["pending", "confirmed", "edited", "rejected"].includes(value);
}

function mapWardrobeCategory(
  value: unknown,
  name: string,
): OutfitWardrobeCategory {
  const category = requiredString(value, name);
  const supported: OutfitWardrobeCategory[] = [
    "top",
    "bottom",
    "dress",
    "outerwear",
    "shoes",
    "bag",
    "accessory",
  ];
  if (!supported.includes(category as OutfitWardrobeCategory)) {
    throw malformedResponse(`${name} is unsupported`);
  }
  return category as OutfitWardrobeCategory;
}

function mapWardrobeSourceType(
  value: unknown,
  name: string,
): OutfitWardrobeSourceType {
  const sourceType = requiredString(value, name);
  if (
    sourceType !== "manual" &&
    sourceType !== "photo" &&
    sourceType !== "product_link"
  ) {
    throw malformedResponse(`${name} is unsupported`);
  }
  return sourceType;
}

async function requireDeletion(path: string): Promise<void> {
  const response = await apiFetch<Normal<unknown>>(path, { method: "DELETE" });
  if (!isRecord(response.data) || response.data.deleted !== true) {
    throw malformedResponse("delete response must confirm deletion");
  }
}

function malformedResponse(reason: string): ApiError {
  return new ApiError(200, `Invalid Outfit response: ${reason}`);
}
