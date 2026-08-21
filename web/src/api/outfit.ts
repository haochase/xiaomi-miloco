import { apiFetch } from "./client";

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
