# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Async orchestration for one explicit Outfit visual-review frame."""

from __future__ import annotations

import asyncio
import hashlib
import math
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from miloco.outfit.try_on import (
    RecommendedOutfitSnapshot,
    TryOnComparison,
    TryOnCorrection,
    build_try_on_correction,
    compare_snapshot_to_observation,
    normalize_visual_observation,
)
from miloco.outfit.visual_budget import (
    VisualBudgetLease,
    VisualBudgetRequest,
    VisualSessionBudgetGuard,
)
from miloco.outfit.visual_observability import build_visual_review_audit_record
from miloco.outfit.visual_ports import (
    CapturedFrame,
    CleanupAuditPort,
    FrameCapturePort,
    OutfitVisionProvider,
    TemporaryMediaStore,
    VisionCandidateItem,
    VisionProviderObservation,
    VisionProviderRejected,
    VisionProviderUsage,
    VisualReviewAuditPort,
)


class VisualReviewStatus(StrEnum):
    """Sanitized terminal status of one explicit visual-review attempt."""

    COMPLETED = "completed"
    REJECTED = "rejected"
    CAPTURE_FAILED = "capture_failed"
    PROVIDER_FAILED = "provider_failed"
    CLEANUP_FAILED = "cleanup_failed"


class VisualReviewRequest(BaseModel):
    """Host-assembled review request with no owner or media-path selector."""

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    snapshot: RecommendedOutfitSnapshot
    explicit_trigger: bool
    session_id: str = Field(min_length=1)
    session_started_at_ms: int = Field(ge=0)
    max_tokens: int = Field(gt=0)


class VisualReviewOutcome(BaseModel):
    """Read-only review outcome without raw media or provider-error details."""

    model_config = ConfigDict(frozen=True)

    status: VisualReviewStatus
    comparison: TryOnComparison | None = None
    correction: TryOnCorrection | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class _ProviderEvaluation:
    outcome: VisualReviewOutcome
    usage: VisionProviderUsage | None = None


class OutfitVisualReviewService:
    """Capture and evaluate one frame only after an explicit user-controlled trigger."""

    def __init__(
        self,
        *,
        capture: FrameCapturePort,
        provider: OutfitVisionProvider,
        temporary_media_store: TemporaryMediaStore,
        enabled: bool,
        provider_timeout_s: float,
        budget_guard: VisualSessionBudgetGuard,
        capture_timeout_s: float = 2.0,
        overall_timeout_s: float = 10.0,
        audit_timeout_s: float = 1.0,
        cleanup_timeout_s: float = 2.0,
        cleanup_audit: CleanupAuditPort | None = None,
        audit: VisualReviewAuditPort | None = None,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        for name, timeout_s in (
            ("capture_timeout_s", capture_timeout_s),
            ("provider_timeout_s", provider_timeout_s),
            ("overall_timeout_s", overall_timeout_s),
            ("audit_timeout_s", audit_timeout_s),
            ("cleanup_timeout_s", cleanup_timeout_s),
        ):
            if not math.isfinite(timeout_s) or timeout_s <= 0:
                raise ValueError(f"{name} must be positive")
        self._capture = capture
        self._provider = provider
        self._temporary_media_store = temporary_media_store
        self._enabled = enabled
        self._capture_timeout_s = capture_timeout_s
        self._provider_timeout_s = provider_timeout_s
        self._overall_timeout_s = overall_timeout_s
        self._audit_timeout_s = audit_timeout_s
        self._cleanup_timeout_s = cleanup_timeout_s
        self._budget_guard = budget_guard
        self._cleanup_audit = cleanup_audit
        self._audit = audit
        self._now_ms = now_ms or _now_ms

    async def evaluate(self, *, request: VisualReviewRequest) -> VisualReviewOutcome:
        """Run at most one capture/provider attempt and clean up its temporary frame."""

        started_ns = time.perf_counter_ns()

        if not self._enabled or not request.explicit_trigger:
            outcome = VisualReviewOutcome(
                status=VisualReviewStatus.REJECTED,
                error_code="explicit_trigger_required",
            )
            await self._record_audit(
                request=request,
                stage="rejected",
                frame_count=0,
                budget_outcome="rejected",
                outcome=outcome,
                started_ns=started_ns,
                usage=None,
                provider_call_count=0,
                usage_complete=False,
            )
            return outcome

        admission = await self._budget_guard.acquire(
            request=VisualBudgetRequest(
                session_id=request.session_id,
                session_started_at_ms=request.session_started_at_ms,
                now_ms=self._now_ms(),
                explicit_trigger=request.explicit_trigger,
                max_tokens=request.max_tokens,
            )
        )
        if not admission.allowed:
            if admission.reason is None:
                raise RuntimeError(
                    "rejected visual budget admission is missing a reason"
                )
            outcome = VisualReviewOutcome(
                status=VisualReviewStatus.REJECTED,
                error_code=admission.reason.value,
            )
            await self._record_audit(
                request=request,
                stage="rejected",
                frame_count=0,
                budget_outcome="rejected",
                outcome=outcome,
                started_ns=started_ns,
                usage=None,
                provider_call_count=0,
                usage_complete=False,
            )
            return outcome
        if admission.lease is None:
            raise RuntimeError("allowed visual budget admission is missing a lease")

        frame: CapturedFrame | None = None
        provider_error: bool | None = None
        usage: VisionProviderUsage | None = None
        outcome: VisualReviewOutcome | None = None
        cancelled = False
        provider_started = asyncio.Event()
        overall_deadline = asyncio.get_running_loop().time() + self._overall_timeout_s
        try:
            capture_timeout_s, capture_timeout_code = _bounded_stage_timeout(
                stage_timeout_s=self._capture_timeout_s,
                overall_deadline=overall_deadline,
                stage_timeout_code="capture_timeout",
            )
            if capture_timeout_s is None:
                outcome = VisualReviewOutcome(
                    status=VisualReviewStatus.CAPTURE_FAILED,
                    error_code=capture_timeout_code,
                )
            else:
                capture_task = asyncio.create_task(
                    self._capture.capture_frame(
                        device_id=request.device_id,
                        request_id=request.request_id,
                    )
                )
                try:
                    frame = await asyncio.wait_for(
                        asyncio.shield(capture_task),
                        timeout=capture_timeout_s,
                    )
                except TimeoutError:
                    frame, recovery_cancelled = await _cancel_capture_and_recover_frame(
                        capture_task
                    )
                    if recovery_cancelled:
                        raise asyncio.CancelledError
                    outcome = VisualReviewOutcome(
                        status=VisualReviewStatus.CAPTURE_FAILED,
                        error_code=capture_timeout_code,
                    )
                except asyncio.CancelledError:
                    frame, _ = await _cancel_capture_and_recover_frame(capture_task)
                    raise
                except Exception:
                    outcome = VisualReviewOutcome(
                        status=VisualReviewStatus.CAPTURE_FAILED,
                        error_code="capture_failed",
                    )
                else:
                    provider_evaluation = await self._evaluate_captured_frame(
                        request=request,
                        frame=frame,
                        overall_deadline=overall_deadline,
                        provider_started=provider_started,
                    )
                    outcome = provider_evaluation.outcome
                    usage = provider_evaluation.usage
                    provider_error = (
                        outcome.status is VisualReviewStatus.PROVIDER_FAILED
                    )
        except asyncio.CancelledError:
            cancelled = True
        finally:
            if provider_started.is_set() and usage is None:
                provider_error = True
            finalizer_task = asyncio.create_task(
                self._finalize_admitted_attempt(
                    request=request,
                    frame=frame,
                    lease=admission.lease,
                    provider_error=provider_error,
                    usage=usage,
                    outcome=outcome,
                )
            )
            outcome, finalizer_cancelled = await _await_shielded_finalizer(
                finalizer_task
            )
            cancelled = cancelled or finalizer_cancelled
        if cancelled:
            provider_call_count = int(provider_started.is_set())
            cancellation_outcome = VisualReviewOutcome(
                status=(
                    VisualReviewStatus.PROVIDER_FAILED
                    if provider_call_count
                    else VisualReviewStatus.CAPTURE_FAILED
                ),
                error_code="request_cancelled",
            )
            await self._record_audit(
                request=request,
                stage="provider" if provider_call_count else "capture",
                frame_count=1 if frame is not None else 0,
                budget_outcome="allowed",
                outcome=cancellation_outcome,
                started_ns=started_ns,
                usage=usage,
                provider_call_count=provider_call_count,
                usage_complete=usage is not None,
            )
            raise asyncio.CancelledError
        if outcome is None:
            raise RuntimeError("visual review ended without a terminal outcome")
        await self._record_audit(
            request=request,
            stage=_audit_stage(outcome.status),
            frame_count=1 if frame is not None else 0,
            budget_outcome="allowed",
            outcome=outcome,
            started_ns=started_ns,
            usage=usage,
            provider_call_count=int(provider_started.is_set()),
            usage_complete=usage is not None,
        )
        return outcome

    async def _finalize_admitted_attempt(
        self,
        *,
        request: VisualReviewRequest,
        frame: CapturedFrame | None,
        lease: VisualBudgetLease,
        provider_error: bool | None,
        usage: VisionProviderUsage | None,
        outcome: VisualReviewOutcome | None,
    ) -> VisualReviewOutcome | None:
        cleanup_failed = False
        if frame is not None:
            cleanup_failed = await self._delete_temporary_frame(frame=frame)

        usage_reject_reason = await self._budget_guard.complete(
            lease=lease,
            provider_error=provider_error,
            actual_tokens=usage.total_tokens if usage is not None else None,
        )
        if cleanup_failed:
            await self._record_cleanup_failure(request=request)
            return VisualReviewOutcome(
                status=VisualReviewStatus.CLEANUP_FAILED,
                error_code="temporary_media_cleanup_failed",
            )
        if usage_reject_reason is not None and (
            outcome is None or outcome.status is VisualReviewStatus.COMPLETED
        ):
            return VisualReviewOutcome(
                status=VisualReviewStatus.PROVIDER_FAILED,
                error_code=usage_reject_reason.value,
            )
        return outcome

    async def _delete_temporary_frame(self, *, frame: CapturedFrame) -> bool:
        delete_task = asyncio.create_task(
            self._temporary_media_store.delete_frame(frame=frame)
        )
        try:
            completed_tasks, _ = await asyncio.wait(
                {delete_task},
                timeout=self._cleanup_timeout_s,
            )
        except asyncio.CancelledError:
            _cancel_and_drain_delete_task(delete_task)
            raise
        if not completed_tasks:
            _cancel_and_drain_delete_task(delete_task)
            return True
        try:
            delete_task.result()
        except asyncio.CancelledError:
            return True
        except Exception:
            return True
        return False

    async def _record_cleanup_failure(self, *, request: VisualReviewRequest) -> None:
        if self._cleanup_audit is None:
            return
        await self._run_audit_operation(
            self._cleanup_audit.record_cleanup_failure(
                request_id=_audit_identifier(request.request_id),
                device_id=_audit_identifier(request.device_id),
                error_code="temporary_media_cleanup_failed",
            )
        )

    async def _record_audit(
        self,
        *,
        request: VisualReviewRequest,
        stage: str,
        frame_count: int,
        budget_outcome: str,
        outcome: VisualReviewOutcome,
        started_ns: int,
        usage: VisionProviderUsage | None,
        provider_call_count: int,
        usage_complete: bool,
    ) -> None:
        if self._audit is None:
            return
        record = build_visual_review_audit_record(
            request_id=request.request_id,
            device_id=request.device_id,
            stage=stage,  # type: ignore[arg-type]
            trigger_type="single_frame",
            frame_count=frame_count,
            budget_outcome=budget_outcome,  # type: ignore[arg-type]
            status=outcome.status.value,  # type: ignore[arg-type]
            error_code=outcome.error_code,
            elapsed_ms=max(0, (time.perf_counter_ns() - started_ns) // 1_000_000),
            input_tokens=usage.input_tokens if usage is not None else 0,
            output_tokens=usage.output_tokens if usage is not None else 0,
            video_tokens=usage.video_tokens if usage is not None else 0,
            provider_call_count=provider_call_count,
            usage_complete=usage_complete,
        )
        await self._run_audit_operation(self._audit.record_visual_review(record))

    async def _run_audit_operation(self, operation: Awaitable[None]) -> None:
        try:
            await asyncio.wait_for(operation, timeout=self._audit_timeout_s)
        except asyncio.CancelledError:
            current_task = asyncio.current_task()
            if current_task is not None and current_task.cancelling():
                raise
        except Exception:
            # Observability must not turn a bounded review into a failed review.
            pass

    async def _evaluate_captured_frame(
        self,
        *,
        request: VisualReviewRequest,
        frame: CapturedFrame,
        overall_deadline: float,
        provider_started: asyncio.Event,
    ) -> _ProviderEvaluation:
        provider_timeout_s, provider_timeout_code = _bounded_stage_timeout(
            stage_timeout_s=self._provider_timeout_s,
            overall_deadline=overall_deadline,
            stage_timeout_code="provider_timeout",
        )
        if provider_timeout_s is None:
            return _ProviderEvaluation(
                outcome=VisualReviewOutcome(
                    status=VisualReviewStatus.PROVIDER_FAILED,
                    error_code=provider_timeout_code,
                )
            )
        provider_started.set()
        provider_task = asyncio.create_task(
            self._provider.observe(
                frame=frame,
                candidate_items=_candidate_items(request.snapshot),
                max_tokens=request.max_tokens,
            )
        )
        try:
            completed_tasks, _ = await asyncio.wait(
                {provider_task},
                timeout=provider_timeout_s,
            )
        except asyncio.CancelledError:
            _cancel_and_drain_provider_task(provider_task)
            raise
        if not completed_tasks:
            _cancel_and_drain_provider_task(provider_task)
            return _ProviderEvaluation(
                outcome=VisualReviewOutcome(
                    status=VisualReviewStatus.PROVIDER_FAILED,
                    error_code=provider_timeout_code,
                )
            )
        try:
            raw_provider_observation = provider_task.result()
        except asyncio.CancelledError:
            raise
        except VisionProviderRejected as exc:
            return _ProviderEvaluation(
                outcome=VisualReviewOutcome(
                    status=VisualReviewStatus.PROVIDER_FAILED,
                    error_code="provider_failed",
                ),
                usage=exc.usage,
            )
        except Exception:
            return _ProviderEvaluation(
                outcome=VisualReviewOutcome(
                    status=VisualReviewStatus.PROVIDER_FAILED,
                    error_code="provider_failed",
                )
            )

        usage = _validated_provider_usage(raw_provider_observation)
        if usage is None:
            return _ProviderEvaluation(
                outcome=VisualReviewOutcome(
                    status=VisualReviewStatus.PROVIDER_FAILED,
                    error_code="usage_unavailable",
                )
            )
        if usage.total_tokens > request.max_tokens:
            return _ProviderEvaluation(
                outcome=VisualReviewOutcome(
                    status=VisualReviewStatus.PROVIDER_FAILED,
                    error_code="token_budget_exceeded",
                ),
                usage=usage,
            )
        try:
            provider_observation = VisionProviderObservation.model_validate(
                raw_provider_observation,
                from_attributes=True,
            )
        except ValidationError:
            return _ProviderEvaluation(
                outcome=VisualReviewOutcome(
                    status=VisualReviewStatus.PROVIDER_FAILED,
                    error_code="provider_failed",
                ),
                usage=usage,
            )
        observation = normalize_visual_observation(
            snapshot=request.snapshot,
            observed_item_ids=provider_observation.observed_item_ids,
            confidence=provider_observation.confidence,
            status=provider_observation.status,
            uncertainty_reason=provider_observation.uncertainty_reason,
        )
        comparison = compare_snapshot_to_observation(request.snapshot, observation)
        return _ProviderEvaluation(
            outcome=VisualReviewOutcome(
                status=VisualReviewStatus.COMPLETED,
                comparison=comparison,
                correction=build_try_on_correction(comparison),
            ),
            usage=usage,
        )


def _validated_provider_usage(
    provider_observation: object,
) -> VisionProviderUsage | None:
    if isinstance(provider_observation, Mapping):
        raw_usage = provider_observation.get("usage")
    else:
        raw_usage = getattr(provider_observation, "usage", None)
    try:
        return VisionProviderUsage.model_validate(raw_usage)
    except ValidationError:
        return None


async def _cancel_capture_and_recover_frame(
    capture_task: asyncio.Task[CapturedFrame],
) -> tuple[CapturedFrame | None, bool]:
    cancelled = False
    if not capture_task.done():
        capture_task.cancel()
    while True:
        try:
            return await asyncio.shield(capture_task), cancelled
        except asyncio.CancelledError:
            current_task = asyncio.current_task()
            if current_task is not None and current_task.cancelling():
                cancelled = True
            if capture_task.done():
                if capture_task.cancelled():
                    return None, cancelled
                try:
                    return capture_task.result(), cancelled
                except Exception:
                    return None, cancelled
        except Exception:
            return None, cancelled


def _cancel_and_drain_provider_task(
    provider_task: asyncio.Task[VisionProviderObservation],
) -> None:
    if not provider_task.done():
        provider_task.cancel()
    provider_task.add_done_callback(_drain_provider_task)


def _drain_provider_task(
    provider_task: asyncio.Task[VisionProviderObservation],
) -> None:
    try:
        provider_task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


def _cancel_and_drain_delete_task(delete_task: asyncio.Task[None]) -> None:
    if not delete_task.done():
        delete_task.cancel()
    delete_task.add_done_callback(_drain_delete_task)


def _drain_delete_task(delete_task: asyncio.Task[None]) -> None:
    try:
        delete_task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def _await_shielded_finalizer(
    finalizer_task: asyncio.Task[VisualReviewOutcome | None],
) -> tuple[VisualReviewOutcome | None, bool]:
    cancelled = False
    while True:
        try:
            return await asyncio.shield(finalizer_task), cancelled
        except asyncio.CancelledError:
            cancelled = True
            if finalizer_task.done():
                return finalizer_task.result(), cancelled


def _bounded_stage_timeout(
    *,
    stage_timeout_s: float,
    overall_deadline: float,
    stage_timeout_code: str,
) -> tuple[float | None, str]:
    remaining_s = overall_deadline - asyncio.get_running_loop().time()
    if remaining_s <= 0:
        return None, "overall_timeout"
    if remaining_s <= stage_timeout_s:
        return remaining_s, "overall_timeout"
    return stage_timeout_s, stage_timeout_code


def _candidate_items(
    snapshot: RecommendedOutfitSnapshot,
) -> tuple[VisionCandidateItem, ...]:
    """Expose only the selected recommendation's IDs as minimum provider context."""

    return tuple(
        VisionCandidateItem(item_id=item_id, description=item_id)
        for item_id in snapshot.item_ids
    )


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _audit_identifier(value: str) -> str:
    """Hash request/device identifiers before sending them to host audit sinks."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _audit_stage(status: VisualReviewStatus) -> str:
    if status is VisualReviewStatus.COMPLETED:
        return "completed"
    if status is VisualReviewStatus.CAPTURE_FAILED:
        return "capture"
    if status is VisualReviewStatus.PROVIDER_FAILED:
        return "provider"
    if status is VisualReviewStatus.CLEANUP_FAILED:
        return "cleanup"
    return "rejected"
