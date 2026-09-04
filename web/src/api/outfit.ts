import { apiFetch } from "./client";

const PROVIDER_STATUSES = new Set([
  "never_called",
  "last_success",
  "last_error",
  "budget_blocked",
  "not_configured",
] as const);

const CAPABILITY_FIELDS = [
  "enabled",
  "primary_person_configured",
  "storage_ready",
  "voice_ingress_configured",
  "camera_allowlisted",
  "last_provider_status",
] as const;

const USAGE_FIELDS = [
  "date",
  "timezone",
  "call_count",
  "input_tokens",
  "output_tokens",
  "estimated_total_tokens",
  "complete",
] as const;

const WARDROBE_DRAFT_FIELDS = [
  "draft_id",
  "name",
  "category",
  "source_types",
  "status",
] as const;

const WARDROBE_ITEM_FIELDS = [
  "item_id",
  "name",
  "category",
  "source_types",
  "status",
  "availability",
] as const;

const RECOMMENDATION_FIELDS = [
  "snapshot_id",
  "context",
  "status",
  "option_item_ids",
  "ranking_version",
  "created_at_ms",
] as const;

const RECOMMENDATION_CONTEXT_FIELDS = [
  "occasion",
  "activity",
  "day_kind",
] as const;

const RECOMMENDATION_DAY_KINDS = new Set([
  "workday",
  "weekend",
  "holiday",
  "unknown",
] as const);

const WARDROBE_CATEGORIES = new Set([
  "top",
  "bottom",
  "dress",
  "outerwear",
  "shoes",
  "bag",
  "accessory",
] as const);

const WARDROBE_SOURCE_TYPES = new Set([
  "manual",
  "photo",
  "product_link",
] as const);

export type OutfitProviderStatus =
  | "never_called"
  | "last_success"
  | "last_error"
  | "budget_blocked"
  | "not_configured";

export interface OutfitCapability {
  enabled: boolean;
  primaryPersonConfigured: boolean;
  storageReady: boolean;
  voiceIngressConfigured: boolean;
  cameraAllowlisted: boolean;
  lastProviderStatus: OutfitProviderStatus;
}

export interface OutfitUsageToday {
  date: string;
  timezone: "Asia/Shanghai";
  callCount: number;
  inputTokens: number | null;
  outputTokens: number | null;
  estimatedTotalTokens: number | null;
  complete: boolean;
}

export type OutfitWardrobeCategory =
  | "top"
  | "bottom"
  | "dress"
  | "outerwear"
  | "shoes"
  | "bag"
  | "accessory";

export type OutfitWardrobeSourceType = "manual" | "photo" | "product_link";

export interface OutfitWardrobeDraft {
  draftId: string;
  name: string;
  category: OutfitWardrobeCategory;
  sourceTypes: OutfitWardrobeSourceType[];
  status: "pending";
}

export interface OutfitWardrobeItem {
  itemId: string;
  name: string;
  category: OutfitWardrobeCategory;
  sourceTypes: OutfitWardrobeSourceType[];
  status: "confirmed";
  availability: "available";
}

export interface OutfitWardrobe {
  pendingDrafts: OutfitWardrobeDraft[];
  availableItems: OutfitWardrobeItem[];
}

export type OutfitRecommendationDayKind =
  | "workday"
  | "weekend"
  | "holiday"
  | "unknown";

export type OutfitRecommendationStatus = "ready" | "insufficient_inventory";

export interface OutfitRecommendationRequest {
  occasion?: string | null;
  activity?: string | null;
  dayKind: OutfitRecommendationDayKind;
}

export interface OutfitRecommendationSnapshot {
  snapshotId: string;
  context: {
    occasion: string | null;
    activity: string | null;
    dayKind: OutfitRecommendationDayKind;
  };
  status: OutfitRecommendationStatus;
  optionItemIds: string[][];
  rankingVersion: string;
  createdAtMs: number;
}

type RecordPayload = Record<string, unknown>;

function hasExactlyKeys(
  value: unknown,
  fields: readonly string[],
): value is RecordPayload {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const keys = Object.keys(value);
  return keys.length === fields.length && fields.every((field) => keys.includes(field));
}

function isValidDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function isNonNegativeSafeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isNonEmptyText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isNullableNonEmptyText(value: unknown): value is string | null {
  return value === null || isNonEmptyText(value);
}

function parseOutfitWardrobeSourceTypes(
  value: unknown,
): OutfitWardrobeSourceType[] {
  if (
    !Array.isArray(value) ||
    !value.every(
      (sourceType) =>
        typeof sourceType === "string" &&
        WARDROBE_SOURCE_TYPES.has(sourceType as OutfitWardrobeSourceType),
    )
  ) {
    throw new Error("invalid outfit wardrobe response");
  }
  return value as OutfitWardrobeSourceType[];
}

function parseOutfitWardrobeDrafts(response: unknown): OutfitWardrobeDraft[] {
  if (!Array.isArray(response)) {
    throw new Error("invalid outfit wardrobe response");
  }
  return response.map((draft) => {
    if (
      !hasExactlyKeys(draft, WARDROBE_DRAFT_FIELDS) ||
      !isNonEmptyText(draft.draft_id) ||
      !isNonEmptyText(draft.name) ||
      typeof draft.category !== "string" ||
      !WARDROBE_CATEGORIES.has(draft.category as OutfitWardrobeCategory) ||
      draft.status !== "pending"
    ) {
      throw new Error("invalid outfit wardrobe response");
    }
    return {
      draftId: draft.draft_id,
      name: draft.name,
      category: draft.category as OutfitWardrobeCategory,
      sourceTypes: parseOutfitWardrobeSourceTypes(draft.source_types),
      status: "pending",
    };
  });
}

function parseOutfitWardrobeItems(response: unknown): OutfitWardrobeItem[] {
  if (!Array.isArray(response)) {
    throw new Error("invalid outfit wardrobe response");
  }
  return response.map((item) => {
    if (
      !hasExactlyKeys(item, WARDROBE_ITEM_FIELDS) ||
      !isNonEmptyText(item.item_id) ||
      !isNonEmptyText(item.name) ||
      typeof item.category !== "string" ||
      !WARDROBE_CATEGORIES.has(item.category as OutfitWardrobeCategory) ||
      item.status !== "confirmed" ||
      item.availability !== "available"
    ) {
      throw new Error("invalid outfit wardrobe response");
    }
    return {
      itemId: item.item_id,
      name: item.name,
      category: item.category as OutfitWardrobeCategory,
      sourceTypes: parseOutfitWardrobeSourceTypes(item.source_types),
      status: "confirmed",
      availability: "available",
    };
  });
}

function parseOutfitRecommendation(
  response: unknown,
): OutfitRecommendationSnapshot {
  if (!hasExactlyKeys(response, RECOMMENDATION_FIELDS)) {
    throw new Error("invalid outfit recommendation response");
  }
  const context = response.context;
  const status = response.status;
  const options = response.option_item_ids;
  if (
    !/^rec-[a-z0-9][a-z0-9-]{0,63}$/.test(String(response.snapshot_id)) ||
    !hasExactlyKeys(context, RECOMMENDATION_CONTEXT_FIELDS) ||
    !isNullableNonEmptyText(context.occasion) ||
    !isNullableNonEmptyText(context.activity) ||
    typeof context.day_kind !== "string" ||
    !RECOMMENDATION_DAY_KINDS.has(
      context.day_kind as OutfitRecommendationDayKind,
    ) ||
    (status !== "ready" && status !== "insufficient_inventory") ||
    !Array.isArray(options) ||
    !isNonEmptyText(response.ranking_version) ||
    !isNonNegativeSafeInteger(response.created_at_ms)
  ) {
    throw new Error("invalid outfit recommendation response");
  }
  if (
    !options.every(
      (option) =>
        Array.isArray(option) &&
        option.length >= 2 &&
        option.every((itemId) => isNonEmptyText(itemId)),
    ) ||
    (status === "ready" && (options.length < 2 || options.length > 3)) ||
    (status === "insufficient_inventory" && options.length > 1)
  ) {
    throw new Error("invalid outfit recommendation response");
  }
  return {
    snapshotId: response.snapshot_id as string,
    context: {
      occasion: context.occasion,
      activity: context.activity,
      dayKind: context.day_kind as OutfitRecommendationDayKind,
    },
    status,
    optionItemIds: options as string[][],
    rankingVersion: response.ranking_version,
    createdAtMs: response.created_at_ms,
  };
}

function parseOutfitCapability(response: unknown): OutfitCapability {
  if (!hasExactlyKeys(response, CAPABILITY_FIELDS)) {
    throw new Error("invalid outfit capability response");
  }
  const providerStatus = response.last_provider_status;
  if (
    typeof response.enabled !== "boolean" ||
    typeof response.primary_person_configured !== "boolean" ||
    typeof response.storage_ready !== "boolean" ||
    typeof response.voice_ingress_configured !== "boolean" ||
    typeof response.camera_allowlisted !== "boolean" ||
    typeof providerStatus !== "string" ||
    !PROVIDER_STATUSES.has(providerStatus as OutfitProviderStatus)
  ) {
    throw new Error("invalid outfit capability response");
  }

  return {
    enabled: response.enabled,
    primaryPersonConfigured: response.primary_person_configured,
    storageReady: response.storage_ready,
    voiceIngressConfigured: response.voice_ingress_configured,
    cameraAllowlisted: response.camera_allowlisted,
    lastProviderStatus: providerStatus as OutfitProviderStatus,
  };
}

function parseOutfitUsageToday(response: unknown): OutfitUsageToday {
  if (!hasExactlyKeys(response, USAGE_FIELDS)) {
    throw new Error("invalid outfit usage response");
  }
  const { input_tokens, output_tokens, estimated_total_tokens } = response;
  if (
    !isValidDate(response.date) ||
    response.timezone !== "Asia/Shanghai" ||
    !isNonNegativeSafeInteger(response.call_count) ||
    typeof response.complete !== "boolean"
  ) {
    throw new Error("invalid outfit usage response");
  }

  if (response.complete) {
    if (
      !isNonNegativeSafeInteger(input_tokens) ||
      !isNonNegativeSafeInteger(output_tokens) ||
      !isNonNegativeSafeInteger(estimated_total_tokens)
    ) {
      throw new Error("invalid outfit usage response");
    }
    return {
      date: response.date,
      timezone: "Asia/Shanghai",
      callCount: response.call_count,
      inputTokens: input_tokens,
      outputTokens: output_tokens,
      estimatedTotalTokens: estimated_total_tokens,
      complete: true,
    };
  }

  if (
    input_tokens !== null ||
    output_tokens !== null ||
    estimated_total_tokens !== null
  ) {
    throw new Error("invalid outfit usage response");
  }

  return {
    date: response.date,
    timezone: "Asia/Shanghai",
    callCount: response.call_count,
    inputTokens: null,
    outputTokens: null,
    estimatedTotalTokens: null,
    complete: false,
  };
}

/** Read the authenticated, side-effect-free Outfit capability snapshot. */
export async function getOutfitCapability(): Promise<OutfitCapability> {
  const response = await apiFetch<unknown>("/api/outfit/capability", {
    method: "GET",
  });
  return parseOutfitCapability(response);
}

/** Read the authenticated, local-day Outfit usage snapshot for diagnostics. */
export async function getOutfitUsageToday(): Promise<OutfitUsageToday> {
  const response = await apiFetch<unknown>("/api/outfit/admin/usage/today", {
    method: "GET",
  });
  return parseOutfitUsageToday(response);
}

/** Read pending and confirmed-available inventory without an owner selector. */
export async function getOutfitWardrobe(): Promise<OutfitWardrobe> {
  const [drafts, items] = await Promise.all([
    apiFetch<unknown>("/api/outfit/wardrobe/drafts", { method: "GET" }),
    apiFetch<unknown>("/api/outfit/wardrobe/items/available", { method: "GET" }),
  ]);
  return {
    pendingDrafts: parseOutfitWardrobeDrafts(drafts),
    availableItems: parseOutfitWardrobeItems(items),
  };
}

/** Create one bounded recommendation from scenario facts only. */
export async function requestOutfitRecommendation(
  request: OutfitRecommendationRequest,
): Promise<OutfitRecommendationSnapshot> {
  const occasion = request.occasion?.trim() || null;
  const activity = request.activity?.trim() || null;
  if (!occasion && !activity) {
    throw new Error("outfit recommendation requires scenario context");
  }
  const response = await apiFetch<unknown>("/api/outfit/recommendations", {
    method: "POST",
    body: JSON.stringify({
      occasion,
      activity,
      day_kind: request.dayKind,
    }),
  });
  return parseOutfitRecommendation(response);
}

/** Backend terminal states exposed by the low-sensitivity visual trigger route. */
export type VisualReviewStatus =
  | "completed"
  | "rejected"
  | "capture_failed"
  | "provider_failed"
  | "cleanup_failed";

/** Sanitized error codes paired with one terminal visual-review status. */
export type VisualReviewErrorCode =
  | "explicit_trigger_required"
  | "session_expired"
  | "concurrent_request_limit"
  | "model_call_limit"
  | "token_budget_exceeded"
  | "usage_unavailable"
  | "provider_error_limit"
  | "session_start_in_future"
  | "session_start_mismatch"
  | "capture_failed"
  | "capture_timeout"
  | "overall_timeout"
  | "provider_failed"
  | "provider_timeout"
  | "temporary_media_cleanup_failed";

export interface VisualReviewTrigger {
  triggerId: string;
  recommendationId: string;
  deviceId: string;
}

export interface VisualReviewResult {
  status: VisualReviewStatus;
  errorCode: VisualReviewErrorCode | null;
}

interface BackendVisualReviewResult {
  status: string;
  error_code: string | null;
}

const VISUAL_REVIEW_ERROR_CODES_BY_STATUS = {
  completed: new Set<VisualReviewErrorCode | null>([null]),
  rejected: new Set<VisualReviewErrorCode | null>([
    "explicit_trigger_required",
    "session_expired",
    "concurrent_request_limit",
    "model_call_limit",
    "token_budget_exceeded",
    "usage_unavailable",
    "provider_error_limit",
    "session_start_in_future",
    "session_start_mismatch",
  ]),
  capture_failed: new Set<VisualReviewErrorCode | null>([
    "capture_failed",
    "capture_timeout",
    "overall_timeout",
  ]),
  provider_failed: new Set<VisualReviewErrorCode | null>([
    "provider_failed",
    "provider_timeout",
    "overall_timeout",
    "usage_unavailable",
    "token_budget_exceeded",
  ]),
  cleanup_failed: new Set<VisualReviewErrorCode | null>([
    "temporary_media_cleanup_failed",
  ]),
} satisfies Readonly<
  Record<VisualReviewStatus, ReadonlySet<VisualReviewErrorCode | null>>
>;

/**
 * Request one user-triggered frame review.
 *
 * The backend owns the primary user, snapshot, media and budget. Keeping the
 * browser payload to these three opaque identifiers prevents the panel from
 * selecting an owner, local path or arbitrary candidate list.
 */
export async function requestVisualReview(
  trigger: VisualReviewTrigger,
): Promise<VisualReviewResult> {
  const response = await apiFetch<BackendVisualReviewResult>(
    "/api/outfit/try-on/review",
    {
      method: "POST",
      body: JSON.stringify({
        trigger_id: trigger.triggerId,
        recommendation_id: trigger.recommendationId,
        device_id: trigger.deviceId,
      }),
    },
  );
  return parseVisualReviewResult(response);
}

function parseVisualReviewResult(
  response: BackendVisualReviewResult,
): VisualReviewResult {
  if (
    !response ||
    typeof response.status !== "string" ||
    !Object.hasOwn(VISUAL_REVIEW_ERROR_CODES_BY_STATUS, response.status) ||
    (response.error_code !== null && typeof response.error_code !== "string")
  ) {
    throw new Error("invalid visual review response");
  }

  const status = response.status as VisualReviewStatus;
  const errorCode = response.error_code as VisualReviewErrorCode | null;
  if (!VISUAL_REVIEW_ERROR_CODES_BY_STATUS[status].has(errorCode)) {
    throw new Error("invalid visual review response");
  }

  return {
    status,
    errorCode,
  };
}
