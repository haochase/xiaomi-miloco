# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Async orchestration tests for explicit, temporary Outfit visual review."""

import asyncio
import hashlib
import math
from types import SimpleNamespace

import pytest
from miloco.outfit.composition import OutfitCandidate
from miloco.outfit.ranking import rank_outfit_candidates
from miloco.outfit.try_on import snapshot_recommended_outfit
from miloco.outfit.visual_budget import VisualBudgetRequest, VisualSessionBudgetGuard
from miloco.outfit.visual_ports import (
    CapturedFrame,
    CleanupAuditPort,
    FrameCapturePort,
    OutfitVisionProvider,
    TemporaryMediaStore,
    VisionCandidateItem,
    VisionProviderObservation,
    VisualReviewAuditPort,
)
from miloco.outfit.visual_service import (
    OutfitVisualReviewService,
    VisualReviewRequest,
    VisualReviewStatus,
)


def _observation(
    *,
    observed_item_ids: tuple[str, ...],
    confidence: float,
    status: str = "observed",
    uncertainty_reason: str | None = None,
) -> VisionProviderObservation:
    return VisionProviderObservation(
        observed_item_ids=observed_item_ids,
        confidence=confidence,
        status=status,
        uncertainty_reason=uncertainty_reason,
        usage={"input_tokens": 8, "output_tokens": 2, "video_tokens": 0},
    )


class _RecordingCapture(FrameCapturePort):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def capture_frame(self, *, device_id: str, request_id: str) -> CapturedFrame:
        self.calls.append((device_id, request_id))
        return CapturedFrame(
            request_id=request_id,
            device_id=device_id,
            media_token="temporary-frame-token",
        )


class _OfflineCapture(_RecordingCapture):
    async def capture_frame(self, *, device_id: str, request_id: str) -> CapturedFrame:
        self.calls.append((device_id, request_id))
        raise RuntimeError("camera offline")


class _HangingCapture(_RecordingCapture):
    def __init__(self) -> None:
        super().__init__()
        self.cancelled = False

    async def capture_frame(self, *, device_id: str, request_id: str) -> CapturedFrame:
        self.calls.append((device_id, request_id))
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class _CancellationReturningCapture(_RecordingCapture):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()

    async def capture_frame(self, *, device_id: str, request_id: str) -> CapturedFrame:
        self.calls.append((device_id, request_id))
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return CapturedFrame(
                request_id=request_id,
                device_id=device_id,
                media_token="late-captured-frame-token",
            )


class _DelayedCancellationReturningCapture(_RecordingCapture):
    def __init__(self) -> None:
        super().__init__()
        self.cancellation_received = asyncio.Event()
        self.allow_return = asyncio.Event()

    async def capture_frame(self, *, device_id: str, request_id: str) -> CapturedFrame:
        self.calls.append((device_id, request_id))
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancellation_received.set()
            await self.allow_return.wait()
            return CapturedFrame(
                request_id=request_id,
                device_id=device_id,
                media_token="overlap-captured-frame-token",
            )


class _SlowCapture(_RecordingCapture):
    async def capture_frame(self, *, device_id: str, request_id: str) -> CapturedFrame:
        await asyncio.sleep(0.02)
        return await super().capture_frame(device_id=device_id, request_id=request_id)


class _RecordingProvider(OutfitVisionProvider):
    def __init__(self, observation: VisionProviderObservation) -> None:
        self.observation = observation
        self.calls: list[tuple[str, tuple[VisionCandidateItem, ...], int]] = []

    async def observe(
        self,
        *,
        frame: CapturedFrame,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> VisionProviderObservation:
        self.calls.append((frame.media_token, candidate_items, max_tokens))
        return self.observation


class _FailingProvider(_RecordingProvider):
    async def observe(
        self,
        *,
        frame: CapturedFrame,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> VisionProviderObservation:
        await super().observe(
            frame=frame,
            candidate_items=candidate_items,
            max_tokens=max_tokens,
        )
        raise RuntimeError("provider unavailable")


class _CancelOnceProvider(_RecordingProvider):
    async def observe(
        self,
        *,
        frame: CapturedFrame,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> VisionProviderObservation:
        await super().observe(
            frame=frame,
            candidate_items=candidate_items,
            max_tokens=max_tokens,
        )
        if len(self.calls) == 1:
            raise asyncio.CancelledError
        return self.observation


class _HangingProvider(OutfitVisionProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def observe(
        self,
        *,
        frame: CapturedFrame,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> VisionProviderObservation:
        self.calls += 1
        await asyncio.Event().wait()


class _HardBudgetProvider:
    def __init__(self, *, total_tokens: int = 10) -> None:
        self.total_tokens = total_tokens
        self.max_tokens_seen: list[int] = []

    async def observe(
        self,
        *,
        frame: CapturedFrame,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> VisionProviderObservation:
        self.max_tokens_seen.append(max_tokens)
        return VisionProviderObservation(
            observed_item_ids=(candidate_items[0].item_id,),
            confidence=0.95,
            usage={
                "input_tokens": self.total_tokens - 2,
                "output_tokens": 2,
                "video_tokens": 0,
            },
        )


class _MissingUsageProvider:
    async def observe(
        self,
        *,
        frame: CapturedFrame,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> object:
        return SimpleNamespace(
            observed_item_ids=(candidate_items[0].item_id,),
            confidence=0.95,
            status="observed",
            uncertainty_reason=None,
        )


class _ConcurrentUsageProvider(OutfitVisionProvider):
    def __init__(self) -> None:
        self.started_request_ids: set[str] = set()
        self.all_started = asyncio.Event()
        self.release = {
            "over-budget-request": asyncio.Event(),
            "legal-request": asyncio.Event(),
        }

    async def observe(
        self,
        *,
        frame: CapturedFrame,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> VisionProviderObservation:
        self.started_request_ids.add(frame.request_id)
        if len(self.started_request_ids) == 2:
            self.all_started.set()
        await self.release[frame.request_id].wait()
        total_tokens = 11 if frame.request_id == "over-budget-request" else 10
        return VisionProviderObservation(
            observed_item_ids=(candidate_items[0].item_id,),
            confidence=0.95,
            usage={
                "input_tokens": total_tokens - 2,
                "output_tokens": 2,
                "video_tokens": 0,
            },
        )


class _CancellationSwallowingLateFailProvider(OutfitVisionProvider):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancellation_received = asyncio.Event()
        self.allow_finish = asyncio.Event()
        self.finished = asyncio.Event()

    async def observe(
        self,
        *,
        frame: CapturedFrame,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> VisionProviderObservation:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancellation_received.set()
            await self.allow_finish.wait()
            raise RuntimeError("late private provider failure")
        finally:
            self.finished.set()


class _FakeVisionPayloadPort:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    async def observe_payload(
        self,
        *,
        media_token: str,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> dict[str, object]:
        assert media_token == "temporary-frame-token"
        assert tuple(item.item_id for item in candidate_items) == (
            "navy-top",
            "gray-bottom",
            "white-shoes",
        )
        assert max_tokens == 10
        return self.payload


class _RecordingMediaStore(TemporaryMediaStore):
    def __init__(self) -> None:
        self.deleted_tokens: list[str] = []

    async def delete_frame(self, *, frame: CapturedFrame) -> None:
        self.deleted_tokens.append(frame.media_token)


class _FailingMediaStore(_RecordingMediaStore):
    async def delete_frame(self, *, frame: CapturedFrame) -> None:
        raise RuntimeError("filesystem path must not leak")


class _ShieldedMediaStore(_RecordingMediaStore):
    def __init__(self) -> None:
        super().__init__()
        self.cleanup_started = asyncio.Event()
        self.allow_cleanup = asyncio.Event()

    async def delete_frame(self, *, frame: CapturedFrame) -> None:
        self.cleanup_started.set()
        await self.allow_cleanup.wait()
        await super().delete_frame(frame=frame)


class _CancellationSwallowingDeleteStore(_RecordingMediaStore):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.cancellation_received = asyncio.Event()
        self.allow_late_completion = asyncio.Event()
        self.finished = asyncio.Event()

    async def delete_frame(self, *, frame: CapturedFrame) -> None:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancellation_received.set()
            await self.allow_late_completion.wait()
            self.deleted_tokens.append(frame.media_token)
        finally:
            self.finished.set()


class _RecordingCleanupAudit(CleanupAuditPort):
    def __init__(self) -> None:
        self.records: list[tuple[str, str, str]] = []

    async def record_cleanup_failure(
        self,
        *,
        request_id: str,
        device_id: str,
        error_code: str,
    ) -> None:
        self.records.append((request_id, device_id, error_code))


class _RecordingVisualAudit(VisualReviewAuditPort):
    def __init__(self) -> None:
        self.records = []

    async def record_visual_review(self, record) -> None:
        self.records.append(record)


class _FailingVisualAudit(VisualReviewAuditPort):
    async def record_visual_review(self, record) -> None:
        raise RuntimeError("audit sink unavailable")


class _HangingCleanupAudit(CleanupAuditPort):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def record_cleanup_failure(
        self,
        *,
        request_id: str,
        device_id: str,
        error_code: str,
    ) -> None:
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class _HangingVisualAudit(VisualReviewAuditPort):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False

    async def record_visual_review(self, record) -> None:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def _snapshot():
    return snapshot_recommended_outfit(
        recommendation_id="recommendation-1",
        owner_person_id="primary-person",
        option=rank_outfit_candidates(
            [
                OutfitCandidate(
                    item_ids=("navy-top", "gray-bottom", "white-shoes"),
                    pattern="top_bottom_shoes",
                )
            ]
        )[0],
    )


def _request(
    *,
    explicit_trigger: bool = True,
    session_started_at_ms: int = 1_000,
    max_tokens: int = 10,
) -> VisualReviewRequest:
    return VisualReviewRequest(
        request_id="visual-request-1",
        device_id="camera-1",
        snapshot=_snapshot(),
        explicit_trigger=explicit_trigger,
        session_id="visual-session-1",
        session_started_at_ms=session_started_at_ms,
        max_tokens=max_tokens,
    )


def _budget_guard() -> VisualSessionBudgetGuard:
    return VisualSessionBudgetGuard(
        ttl_ms=1_000,
        max_concurrent_requests=1,
        max_model_calls=2,
        max_total_tokens=30,
        max_consecutive_provider_errors=2,
    )


@pytest.mark.asyncio
async def test_disabled_or_non_explicit_review_never_captures_or_calls_provider() -> (
    None
):
    capture = _RecordingCapture()
    provider = _RecordingProvider(
        _observation(observed_item_ids=("navy-top",), confidence=0.95)
    )
    media_store = _RecordingMediaStore()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        enabled=False,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request(explicit_trigger=False))

    assert outcome.status is VisualReviewStatus.REJECTED
    assert capture.calls == []
    assert provider.calls == []
    assert media_store.deleted_tokens == []


@pytest.mark.asyncio
async def test_explicit_review_uses_current_snapshot_candidates_and_deletes_frame() -> (
    None
):
    capture = _RecordingCapture()
    provider = _RecordingProvider(
        _observation(
            observed_item_ids=("navy-top", "gray-bottom"),
            confidence=0.95,
        )
    )
    media_store = _RecordingMediaStore()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.COMPLETED
    assert outcome.comparison is not None
    assert outcome.comparison.status == "mismatch"
    assert outcome.correction is not None
    assert outcome.correction.requires_user_confirmation is True
    assert capture.calls == [("camera-1", "visual-request-1")]
    assert [item.item_id for item in provider.calls[0][1]] == [
        "navy-top",
        "gray-bottom",
        "white-shoes",
    ]
    assert media_store.deleted_tokens == ["temporary-frame-token"]


@pytest.mark.asyncio
async def test_provider_failure_returns_sanitized_error_and_still_deletes_frame() -> (
    None
):
    capture = _RecordingCapture()
    provider = _FailingProvider(
        _observation(observed_item_ids=("navy-top",), confidence=0.95)
    )
    media_store = _RecordingMediaStore()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.PROVIDER_FAILED
    assert outcome.error_code == "provider_failed"
    assert outcome.comparison is None
    assert media_store.deleted_tokens == ["temporary-frame-token"]


@pytest.mark.asyncio
async def test_camera_offline_returns_capture_error_without_provider_or_cleanup() -> (
    None
):
    capture = _OfflineCapture()
    provider = _RecordingProvider(
        _observation(observed_item_ids=("navy-top",), confidence=0.95)
    )
    media_store = _RecordingMediaStore()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.CAPTURE_FAILED
    assert outcome.error_code == "capture_failed"
    assert provider.calls == []
    assert media_store.deleted_tokens == []


@pytest.mark.asyncio
async def test_provider_timeout_returns_sanitized_error_and_still_deletes_frame() -> (
    None
):
    capture = _RecordingCapture()
    provider = _HangingProvider()
    media_store = _RecordingMediaStore()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        enabled=True,
        provider_timeout_s=0.01,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())
    rejected = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.PROVIDER_FAILED
    assert outcome.error_code == "provider_timeout"
    assert rejected.status is VisualReviewStatus.REJECTED
    assert rejected.error_code == "usage_unavailable"
    assert provider.calls == 1
    assert media_store.deleted_tokens == ["temporary-frame-token"]


@pytest.mark.asyncio
async def test_expired_or_over_hard_budget_session_never_captures_a_frame() -> None:
    capture = _RecordingCapture()
    provider = _RecordingProvider(
        _observation(observed_item_ids=("navy-top",), confidence=0.95)
    )
    media_store = _RecordingMediaStore()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    expired = await service.evaluate(request=_request(session_started_at_ms=0))
    over_hard_budget = await service.evaluate(request=_request(max_tokens=31))

    assert expired.error_code == "session_expired"
    assert over_hard_budget.error_code == "token_budget_exceeded"
    assert capture.calls == []
    assert provider.calls == []
    assert media_store.deleted_tokens == []


@pytest.mark.asyncio
async def test_cancelled_provider_attempt_cleans_frame_and_closes_session() -> None:
    capture = _RecordingCapture()
    provider = _CancelOnceProvider(
        _observation(observed_item_ids=("navy-top",), confidence=0.95)
    )
    media_store = _RecordingMediaStore()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    with pytest.raises(asyncio.CancelledError):
        await service.evaluate(request=_request())

    rejected = await service.evaluate(request=_request())

    assert rejected.status is VisualReviewStatus.REJECTED
    assert rejected.error_code == "usage_unavailable"
    assert len(capture.calls) == 1
    assert media_store.deleted_tokens == ["temporary-frame-token"]


@pytest.mark.asyncio
async def test_explicit_provider_uncertainty_remains_non_actionable() -> None:
    capture = _RecordingCapture()
    provider = _RecordingProvider(
        _observation(
            observed_item_ids=(),
            confidence=0.95,
            status="uncertain",
            uncertainty_reason="low_light",
        )
    )
    media_store = _RecordingMediaStore()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.COMPLETED
    assert outcome.comparison is not None
    assert outcome.comparison.status == "uncertain"
    assert outcome.correction is not None
    assert outcome.correction.status == "not_actionable"


@pytest.mark.asyncio
async def test_service_accepts_strict_provider_adapter_without_exposing_payload_details() -> (
    None
):
    from miloco.outfit.vision_provider import ConstrainedVisionProviderAdapter

    capture = _RecordingCapture()
    provider = ConstrainedVisionProviderAdapter(
        payload_port=_FakeVisionPayloadPort(
            {
                "status": "observed",
                "observed_item_ids": ["navy-top", "gray-bottom"],
                "confidence": 0.91,
                "usage": {
                    "input_tokens": 8,
                    "output_tokens": 2,
                    "video_tokens": 0,
                },
            }
        )
    )
    media_store = _RecordingMediaStore()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.COMPLETED
    assert outcome.comparison is not None
    assert outcome.comparison.status == "mismatch"
    assert outcome.error_code is None
    assert media_store.deleted_tokens == ["temporary-frame-token"]


@pytest.mark.asyncio
async def test_cleanup_failure_records_sanitized_audit_warning_without_path_or_error_text() -> (
    None
):
    capture = _RecordingCapture()
    provider = _RecordingProvider(
        _observation(observed_item_ids=("navy-top",), confidence=0.95)
    )
    audit = _RecordingCleanupAudit()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=_FailingMediaStore(),
        cleanup_audit=audit,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.CLEANUP_FAILED
    assert outcome.error_code == "temporary_media_cleanup_failed"
    assert audit.records == [
        (
            hashlib.sha256(b"visual-request-1").hexdigest()[:16],
            hashlib.sha256(b"camera-1").hexdigest()[:16],
            "temporary_media_cleanup_failed",
        )
    ]


@pytest.mark.asyncio
async def test_terminal_review_records_one_sanitized_audit_event() -> None:
    capture = _RecordingCapture()
    provider = _RecordingProvider(
        _observation(observed_item_ids=("navy-top",), confidence=0.95)
    )
    audit = _RecordingVisualAudit()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=_RecordingMediaStore(),
        cleanup_audit=None,
        audit=audit,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.COMPLETED
    assert len(audit.records) == 1
    record = audit.records[0]
    assert record.stage == "completed"
    assert record.trigger_type == "single_frame"
    assert record.frame_count == 1
    assert record.budget_outcome == "allowed"
    assert record.status == "completed"
    assert record.request_id_digest != "visual-request-1"
    assert record.device_id_digest != "camera-1"


@pytest.mark.asyncio
async def test_budget_rejection_records_rejected_audit_without_capture() -> None:
    capture = _RecordingCapture()
    provider = _RecordingProvider(
        _observation(observed_item_ids=("navy-top",), confidence=0.95)
    )
    audit = _RecordingVisualAudit()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=_RecordingMediaStore(),
        audit=audit,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request(max_tokens=31))

    assert outcome.status is VisualReviewStatus.REJECTED
    assert capture.calls == []
    assert provider.calls == []
    assert len(audit.records) == 1
    record = audit.records[0]
    assert record.stage == "rejected"
    assert record.budget_outcome == "rejected"
    assert record.status == "rejected"
    assert record.frame_count == 0
    assert record.error_code == "token_budget_exceeded"


@pytest.mark.asyncio
async def test_audit_sink_failure_does_not_change_review_outcome() -> None:
    service = OutfitVisualReviewService(
        capture=_RecordingCapture(),
        provider=_RecordingProvider(
            _observation(observed_item_ids=("navy-top",), confidence=0.95)
        ),
        temporary_media_store=_RecordingMediaStore(),
        audit=_FailingVisualAudit(),
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.COMPLETED


@pytest.mark.asyncio
async def test_provider_failure_audit_records_provider_stage_without_raw_ids() -> None:
    audit = _RecordingVisualAudit()
    service = OutfitVisualReviewService(
        capture=_RecordingCapture(),
        provider=_FailingProvider(
            _observation(observed_item_ids=("navy-top",), confidence=0.95)
        ),
        temporary_media_store=_RecordingMediaStore(),
        audit=audit,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.PROVIDER_FAILED
    assert len(audit.records) == 1
    record = audit.records[0]
    assert record.stage == "provider"
    assert record.status == "provider_failed"
    assert record.frame_count == 1
    assert "visual-request-1" not in record.model_dump_json()
    assert "camera-1" not in record.model_dump_json()


@pytest.mark.asyncio
async def test_external_cancellation_waits_for_deletion_then_releases_budget_lease() -> (
    None
):
    media_store = _ShieldedMediaStore()
    service = OutfitVisualReviewService(
        capture=_RecordingCapture(),
        provider=_RecordingProvider(
            _observation(observed_item_ids=("navy-top",), confidence=0.95)
        ),
        temporary_media_store=media_store,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )
    review_task = asyncio.create_task(service.evaluate(request=_request()))
    await media_store.cleanup_started.wait()

    review_task.cancel()
    await asyncio.sleep(0)

    assert review_task.done() is False
    review_task.cancel()
    await asyncio.sleep(0)
    assert review_task.done() is False
    media_store.allow_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await review_task
    assert media_store.deleted_tokens == ["temporary-frame-token"]

    recovered = await service.evaluate(request=_request())
    assert recovered.status is VisualReviewStatus.COMPLETED


@pytest.mark.asyncio
async def test_hanging_capture_is_cancelled_at_capture_deadline() -> None:
    capture = _HangingCapture()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=_HangingProvider(),
        temporary_media_store=_RecordingMediaStore(),
        enabled=True,
        capture_timeout_s=0.01,
        provider_timeout_s=1.0,
        overall_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.CAPTURE_FAILED
    assert outcome.error_code == "capture_timeout"
    assert capture.cancelled is True


@pytest.mark.asyncio
async def test_overall_deadline_bounds_capture_plus_provider() -> None:
    service = OutfitVisualReviewService(
        capture=_SlowCapture(),
        provider=_HangingProvider(),
        temporary_media_store=_RecordingMediaStore(),
        enabled=True,
        capture_timeout_s=1.0,
        provider_timeout_s=1.0,
        overall_timeout_s=0.1,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.PROVIDER_FAILED
    assert outcome.error_code == "overall_timeout"


@pytest.mark.asyncio
async def test_hard_provider_budget_is_enforced_and_actual_usage_is_audited() -> None:
    provider = _HardBudgetProvider(total_tokens=10)
    audit = _RecordingVisualAudit()
    service = OutfitVisualReviewService(
        capture=_RecordingCapture(),
        provider=provider,
        temporary_media_store=_RecordingMediaStore(),
        audit=audit,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.COMPLETED
    assert provider.max_tokens_seen == [10]
    assert len(audit.records) == 1
    assert audit.records[0].input_tokens == 8
    assert audit.records[0].output_tokens == 2
    assert audit.records[0].video_tokens == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "error_code"),
    [
        (_MissingUsageProvider(), "usage_unavailable"),
        (_HardBudgetProvider(total_tokens=11), "token_budget_exceeded"),
    ],
)
async def test_invalid_or_over_budget_actual_usage_fails_before_actionable_result(
    provider: object,
    error_code: str,
) -> None:
    service = OutfitVisualReviewService(
        capture=_RecordingCapture(),
        provider=provider,
        temporary_media_store=_RecordingMediaStore(),
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.PROVIDER_FAILED
    assert outcome.error_code == error_code
    assert outcome.comparison is None
    assert outcome.correction is None


@pytest.mark.asyncio
async def test_semantic_provider_rejection_reconciles_and_audits_actual_usage() -> None:
    from miloco.outfit.vision_provider import ConstrainedVisionProviderAdapter

    guard = _budget_guard()
    audit = _RecordingVisualAudit()
    provider = ConstrainedVisionProviderAdapter(
        payload_port=_FakeVisionPayloadPort(
            {
                "status": "observed",
                "observed_item_ids": ["private-unknown-item"],
                "confidence": 0.91,
                "usage": {
                    "input_tokens": 7,
                    "output_tokens": 2,
                    "video_tokens": 1,
                },
            }
        )
    )
    service = OutfitVisualReviewService(
        capture=_RecordingCapture(),
        provider=provider,
        temporary_media_store=_RecordingMediaStore(),
        audit=audit,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=guard,
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())
    next_admission = await guard.acquire(
        request=VisualBudgetRequest(
            session_id="visual-session-1",
            session_started_at_ms=1_000,
            now_ms=1_200,
            explicit_trigger=True,
            max_tokens=21,
        )
    )
    if next_admission.lease is not None:
        await guard.complete(
            lease=next_admission.lease,
            provider_error=True,
            actual_tokens=None,
        )

    assert outcome.status is VisualReviewStatus.PROVIDER_FAILED
    assert outcome.error_code == "provider_failed"
    assert outcome.comparison is None
    assert len(audit.records) == 1
    assert audit.records[0].input_tokens == 7
    assert audit.records[0].output_tokens == 2
    assert audit.records[0].video_tokens == 1
    assert "private-unknown-item" not in audit.records[0].model_dump_json()
    assert next_admission.allowed is False
    assert next_admission.reason == "token_budget_exceeded"


@pytest.mark.asyncio
async def test_budget_lease_is_released_before_cleanup_audit_runs() -> None:
    guard = _budget_guard()
    cleanup_audit = _HangingCleanupAudit()
    service = OutfitVisualReviewService(
        capture=_RecordingCapture(),
        provider=_RecordingProvider(
            _observation(observed_item_ids=("navy-top",), confidence=0.95)
        ),
        temporary_media_store=_FailingMediaStore(),
        cleanup_audit=cleanup_audit,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=guard,
        now_ms=lambda: 1_100,
    )
    review_task = asyncio.create_task(service.evaluate(request=_request()))
    await cleanup_audit.started.wait()

    next_admission = await guard.acquire(
        request=VisualBudgetRequest(
            session_id="visual-session-1",
            session_started_at_ms=1_000,
            now_ms=1_200,
            explicit_trigger=True,
            max_tokens=10,
        )
    )
    if next_admission.lease is not None:
        await guard.complete(
            lease=next_admission.lease,
            provider_error=True,
            actual_tokens=None,
        )
    cleanup_audit.release.set()
    outcome = await review_task

    assert next_admission.allowed is True
    assert outcome.status is VisualReviewStatus.CLEANUP_FAILED


@pytest.mark.asyncio
async def test_hanging_cleanup_audit_times_out_without_blocking_outcome() -> None:
    cleanup_audit = _HangingCleanupAudit()
    service = OutfitVisualReviewService(
        capture=_RecordingCapture(),
        provider=_RecordingProvider(
            _observation(observed_item_ids=("navy-top",), confidence=0.95)
        ),
        temporary_media_store=_FailingMediaStore(),
        cleanup_audit=cleanup_audit,
        enabled=True,
        provider_timeout_s=1.0,
        audit_timeout_s=0.01,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await asyncio.wait_for(service.evaluate(request=_request()), timeout=0.2)

    assert outcome.status is VisualReviewStatus.CLEANUP_FAILED
    assert cleanup_audit.cancelled is True


@pytest.mark.asyncio
async def test_hanging_terminal_audit_times_out_without_blocking_outcome() -> None:
    audit = _HangingVisualAudit()
    service = OutfitVisualReviewService(
        capture=_RecordingCapture(),
        provider=_RecordingProvider(
            _observation(observed_item_ids=("navy-top",), confidence=0.95)
        ),
        temporary_media_store=_RecordingMediaStore(),
        audit=audit,
        enabled=True,
        provider_timeout_s=1.0,
        audit_timeout_s=0.01,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await asyncio.wait_for(service.evaluate(request=_request()), timeout=0.2)

    assert outcome.status is VisualReviewStatus.COMPLETED
    assert audit.cancelled is True


@pytest.mark.asyncio
async def test_cancel_race_recovers_and_deletes_a_completed_capture() -> None:
    capture = _CancellationReturningCapture()
    provider = _RecordingProvider(
        _observation(observed_item_ids=("navy-top",), confidence=0.95)
    )
    media_store = _RecordingMediaStore()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        enabled=True,
        capture_timeout_s=1.0,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )
    review_task = asyncio.create_task(service.evaluate(request=_request()))
    await capture.started.wait()

    review_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await review_task
    assert provider.calls == []
    assert media_store.deleted_tokens == ["late-captured-frame-token"]


@pytest.mark.asyncio
async def test_capture_timeout_recovers_racing_frame_without_calling_provider() -> None:
    capture = _CancellationReturningCapture()
    provider = _RecordingProvider(
        _observation(observed_item_ids=("navy-top",), confidence=0.95)
    )
    media_store = _RecordingMediaStore()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        enabled=True,
        capture_timeout_s=0.01,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(request=_request())

    assert outcome.status is VisualReviewStatus.CAPTURE_FAILED
    assert outcome.error_code == "capture_timeout"
    assert provider.calls == []
    assert media_store.deleted_tokens == ["late-captured-frame-token"]


@pytest.mark.asyncio
async def test_external_cancel_during_timeout_recovery_still_deletes_then_propagates() -> (
    None
):
    capture = _DelayedCancellationReturningCapture()
    provider = _RecordingProvider(
        _observation(observed_item_ids=("navy-top",), confidence=0.95)
    )
    media_store = _RecordingMediaStore()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        enabled=True,
        capture_timeout_s=0.01,
        provider_timeout_s=1.0,
        budget_guard=_budget_guard(),
        now_ms=lambda: 1_100,
    )
    review_task = asyncio.create_task(service.evaluate(request=_request()))
    await capture.cancellation_received.wait()

    review_task.cancel()
    capture.allow_return.set()

    with pytest.raises(asyncio.CancelledError):
        await review_task
    assert provider.calls == []
    assert media_store.deleted_tokens == ["overlap-captured-frame-token"]


@pytest.mark.asyncio
async def test_provider_timeout_hard_returns_and_safely_drains_late_failure() -> None:
    capture = _RecordingCapture()
    provider = _CancellationSwallowingLateFailProvider()
    media_store = _RecordingMediaStore()
    guard = _budget_guard()
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        enabled=True,
        provider_timeout_s=0.01,
        budget_guard=guard,
        now_ms=lambda: 1_100,
    )
    loop = asyncio.get_running_loop()
    unhandled_contexts: list[dict[str, object]] = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(
        lambda _loop, context: unhandled_contexts.append(context)
    )
    review_task = asyncio.create_task(service.evaluate(request=_request()))
    try:
        await provider.cancellation_received.wait()
        completed_tasks, _ = await asyncio.wait({review_task}, timeout=0.2)
        hard_returned = review_task in completed_tasks
        if hard_returned:
            outcome = review_task.result()
        else:
            outcome = None

        provider.allow_finish.set()
        await provider.finished.wait()
        if outcome is None:
            outcome = await review_task
        await asyncio.sleep(0)
    finally:
        provider.allow_finish.set()
        loop.set_exception_handler(previous_handler)

    next_admission = await guard.acquire(
        request=VisualBudgetRequest(
            session_id="visual-session-1",
            session_started_at_ms=1_000,
            now_ms=1_200,
            explicit_trigger=True,
            max_tokens=1,
        )
    )

    assert hard_returned is True
    assert outcome.status is VisualReviewStatus.PROVIDER_FAILED
    assert outcome.error_code == "provider_timeout"
    assert media_store.deleted_tokens == ["temporary-frame-token"]
    assert next_admission.allowed is False
    assert next_admission.reason == "usage_unavailable"
    assert unhandled_contexts == []


@pytest.mark.asyncio
async def test_concurrent_lease_completion_cannot_preserve_actionable_result_after_exhaustion() -> (
    None
):
    provider = _ConcurrentUsageProvider()
    guard = VisualSessionBudgetGuard(
        ttl_ms=1_000,
        max_concurrent_requests=2,
        max_model_calls=3,
        max_total_tokens=30,
        max_consecutive_provider_errors=3,
    )
    service = OutfitVisualReviewService(
        capture=_RecordingCapture(),
        provider=provider,
        temporary_media_store=_RecordingMediaStore(),
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=guard,
        now_ms=lambda: 1_100,
    )
    over_budget_task = asyncio.create_task(
        service.evaluate(
            request=_request().model_copy(update={"request_id": "over-budget-request"})
        )
    )
    legal_task = asyncio.create_task(
        service.evaluate(
            request=_request().model_copy(update={"request_id": "legal-request"})
        )
    )
    await provider.all_started.wait()

    provider.release["over-budget-request"].set()
    over_budget = await over_budget_task
    provider.release["legal-request"].set()
    legal = await legal_task

    assert over_budget.status is VisualReviewStatus.PROVIDER_FAILED
    assert over_budget.error_code == "token_budget_exceeded"
    assert legal.status is VisualReviewStatus.PROVIDER_FAILED
    assert legal.error_code == "token_budget_exceeded"
    assert legal.comparison is None
    assert legal.correction is None


@pytest.mark.parametrize(
    ("field_name", "invalid_timeout"),
    [
        (field_name, invalid_timeout)
        for field_name in (
            "capture_timeout_s",
            "provider_timeout_s",
            "overall_timeout_s",
            "audit_timeout_s",
            "cleanup_timeout_s",
        )
        for invalid_timeout in (math.nan, math.inf, -math.inf)
    ],
)
def test_service_rejects_non_finite_timeouts(
    field_name: str,
    invalid_timeout: float,
) -> None:
    kwargs: dict[str, object] = {
        "capture": _RecordingCapture(),
        "provider": _RecordingProvider(
            _observation(observed_item_ids=("navy-top",), confidence=0.95)
        ),
        "temporary_media_store": _RecordingMediaStore(),
        "enabled": True,
        "capture_timeout_s": 1.0,
        "provider_timeout_s": 1.0,
        "overall_timeout_s": 1.0,
        "audit_timeout_s": 1.0,
        "cleanup_timeout_s": 1.0,
        "budget_guard": _budget_guard(),
    }
    kwargs[field_name] = invalid_timeout

    with pytest.raises(ValueError, match=field_name):
        OutfitVisualReviewService(**kwargs)


@pytest.mark.asyncio
async def test_hanging_delete_times_out_releases_lease_and_drains_late_completion() -> (
    None
):
    media_store = _CancellationSwallowingDeleteStore()
    guard = _budget_guard()
    service = OutfitVisualReviewService(
        capture=_RecordingCapture(),
        provider=_RecordingProvider(
            _observation(observed_item_ids=("navy-top",), confidence=0.95)
        ),
        temporary_media_store=media_store,
        enabled=True,
        provider_timeout_s=1.0,
        cleanup_timeout_s=0.01,
        budget_guard=guard,
        now_ms=lambda: 1_100,
    )
    review_task = asyncio.create_task(service.evaluate(request=_request()))
    try:
        await media_store.cancellation_received.wait()
        completed_tasks, _ = await asyncio.wait({review_task}, timeout=0.2)
        hard_returned = review_task in completed_tasks
        if hard_returned:
            outcome = review_task.result()
        else:
            outcome = None

        next_admission = await guard.acquire(
            request=VisualBudgetRequest(
                session_id="visual-session-1",
                session_started_at_ms=1_000,
                now_ms=1_200,
                explicit_trigger=True,
                max_tokens=10,
            )
        )
        if next_admission.lease is not None:
            await guard.complete(
                lease=next_admission.lease,
                provider_error=False,
                actual_tokens=10,
            )

        media_store.allow_late_completion.set()
        await media_store.finished.wait()
        if outcome is None:
            outcome = await review_task
        await asyncio.sleep(0)
    finally:
        media_store.allow_late_completion.set()

    assert hard_returned is True
    assert outcome.status is VisualReviewStatus.CLEANUP_FAILED
    assert outcome.error_code == "temporary_media_cleanup_failed"
    assert next_admission.allowed is True
    assert media_store.deleted_tokens == ["temporary-frame-token"]
