# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Synthetic visual flow: explicit trigger to non-mutating user review."""

from __future__ import annotations

import pytest
from miloco.outfit.camera_adapter import CameraFrameCaptureAdapter
from miloco.outfit.composition import OutfitCandidate
from miloco.outfit.ranking import rank_outfit_candidates
from miloco.outfit.try_on import snapshot_recommended_outfit
from miloco.outfit.vision_provider import ConstrainedVisionProviderAdapter
from miloco.outfit.visual_budget import VisualSessionBudgetGuard
from miloco.outfit.visual_ports import CapturedFrame, VisionCandidateItem
from miloco.outfit.visual_service import (
    OutfitVisualReviewService,
    VisualReviewRequest,
    VisualReviewStatus,
)


class _CachedFrameReader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def peek_latest_frame(self, did: str, *, window_ms: int = 2_000) -> object:
        self.calls.append((did, window_ms))
        return {"decoded": "synthetic-frame"}


class _TemporaryFrameStore:
    def __init__(self) -> None:
        self.written: list[object] = []
        self.deleted: list[str] = []

    async def write_frame(
        self,
        *,
        decoded_frame: object,
        device_id: str,
        request_id: str,
    ) -> CapturedFrame:
        self.written.append((decoded_frame, device_id, request_id))
        return CapturedFrame(
            request_id=request_id,
            device_id=device_id,
            media_token="opaque-temporary-frame",
        )

    async def delete_frame(self, *, frame: CapturedFrame) -> None:
        self.deleted.append(frame.media_token)


class _PayloadPort:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...], int]] = []

    async def observe_payload(
        self,
        *,
        media_token: str,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> dict[str, object]:
        self.calls.append(
            (media_token, tuple(item.item_id for item in candidate_items), max_tokens)
        )
        return {
            "status": "observed",
            "observed_item_ids": ["navy-top", "gray-bottom"],
            "confidence": 0.95,
            "usage": {
                "input_tokens": 7,
                "output_tokens": 2,
                "video_tokens": 1,
            },
        }


def _snapshot():
    option = rank_outfit_candidates(
        [
            OutfitCandidate(
                item_ids=("navy-top", "gray-bottom", "white-shoes"),
                pattern="top_bottom_shoes",
            )
        ]
    )[0]
    return snapshot_recommended_outfit(
        recommendation_id="recommendation-1",
        owner_person_id="primary-person",
        option=option,
    )


@pytest.mark.asyncio
async def test_explicit_visual_flow_is_candidate_bound_and_non_mutating() -> None:
    snapshot = _snapshot()
    reader = _CachedFrameReader()
    temporary_store = _TemporaryFrameStore()
    payload_port = _PayloadPort()
    service = OutfitVisualReviewService(
        capture=CameraFrameCaptureAdapter(
            latest_frame_reader=reader,
            temporary_frame_writer=temporary_store,
        ),
        provider=ConstrainedVisionProviderAdapter(payload_port=payload_port),
        temporary_media_store=temporary_store,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=VisualSessionBudgetGuard(
            ttl_ms=1_000,
            max_concurrent_requests=1,
            max_model_calls=1,
            max_total_tokens=20,
            max_consecutive_provider_errors=1,
        ),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(
        request=VisualReviewRequest(
            request_id="visual-request-1",
            device_id="camera-1",
            snapshot=snapshot,
            explicit_trigger=True,
            session_id="visual-session-1",
            session_started_at_ms=1_000,
            max_tokens=10,
        )
    )

    assert outcome.status is VisualReviewStatus.COMPLETED
    assert outcome.comparison is not None
    assert outcome.comparison.status == "mismatch"
    assert outcome.correction is not None
    assert outcome.correction.requires_user_confirmation is True
    assert reader.calls == [("camera-1", 2_000)]
    assert temporary_store.written == [
        ({"decoded": "synthetic-frame"}, "camera-1", "visual-request-1")
    ]
    assert payload_port.calls == [
        (
            "opaque-temporary-frame",
            ("navy-top", "gray-bottom", "white-shoes"),
            10,
        )
    ]
    assert temporary_store.deleted == ["opaque-temporary-frame"]
    assert snapshot.item_ids == ("navy-top", "gray-bottom", "white-shoes")
    assert snapshot.owner_person_id == "primary-person"


@pytest.mark.asyncio
async def test_visual_flow_without_explicit_trigger_does_not_read_cached_frame() -> (
    None
):
    reader = _CachedFrameReader()
    temporary_store = _TemporaryFrameStore()
    payload_port = _PayloadPort()
    service = OutfitVisualReviewService(
        capture=CameraFrameCaptureAdapter(
            latest_frame_reader=reader,
            temporary_frame_writer=temporary_store,
        ),
        provider=ConstrainedVisionProviderAdapter(payload_port=payload_port),
        temporary_media_store=temporary_store,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=VisualSessionBudgetGuard(
            ttl_ms=1_000,
            max_concurrent_requests=1,
            max_model_calls=1,
            max_total_tokens=20,
            max_consecutive_provider_errors=1,
        ),
        now_ms=lambda: 1_100,
    )

    outcome = await service.evaluate(
        request=VisualReviewRequest(
            request_id="visual-request-2",
            device_id="camera-1",
            snapshot=_snapshot(),
            explicit_trigger=False,
            session_id="visual-session-1",
            session_started_at_ms=1_000,
            max_tokens=10,
        )
    )

    assert outcome.status is VisualReviewStatus.REJECTED
    assert outcome.error_code == "explicit_trigger_required"
    assert reader.calls == []
    assert temporary_store.written == []
    assert payload_port.calls == []
