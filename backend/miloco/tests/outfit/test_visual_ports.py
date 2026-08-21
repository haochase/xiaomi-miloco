# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Narrow async boundary contracts for user-triggered Outfit visual review."""

import pytest
from miloco.outfit.visual_ports import (
    CapturedFrame,
    FrameCapturePort,
    OutfitVisionProvider,
    TemporaryMediaStore,
    VisionCandidateItem,
    VisionProviderObservation,
)
from pydantic import ValidationError


class _FakeFrameCapture(FrameCapturePort):
    async def capture_frame(self, *, device_id: str, request_id: str) -> CapturedFrame:
        return CapturedFrame(
            request_id=request_id,
            device_id=device_id,
            media_token="temporary-frame-token",
        )


class _FakeVisionProvider(OutfitVisionProvider):
    async def observe(
        self,
        *,
        frame: CapturedFrame,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> VisionProviderObservation:
        assert frame.media_token == "temporary-frame-token"
        assert [candidate.item_id for candidate in candidate_items] == ["navy-top"]
        assert max_tokens == 20
        return VisionProviderObservation(
            observed_item_ids=("navy-top",),
            confidence=0.95,
            usage={"input_tokens": 12, "output_tokens": 3, "video_tokens": 5},
        )


class _FakeTemporaryMediaStore(TemporaryMediaStore):
    async def delete_frame(self, *, frame: CapturedFrame) -> None:
        assert frame.media_token == "temporary-frame-token"


@pytest.mark.asyncio
async def test_async_ports_exchange_only_opaque_temporary_media_and_candidate_scope() -> (
    None
):
    frame = await _FakeFrameCapture().capture_frame(
        device_id="camera-1",
        request_id="request-1",
    )
    observation = await _FakeVisionProvider().observe(
        frame=frame,
        candidate_items=(
            VisionCandidateItem(item_id="navy-top", description="navy top"),
        ),
        max_tokens=20,
    )
    await _FakeTemporaryMediaStore().delete_frame(frame=frame)

    assert observation.observed_item_ids == ("navy-top",)
    assert observation.confidence == 0.95
    assert observation.usage.total_tokens == 20


def test_captured_frame_is_immutable_and_never_exposes_a_local_path() -> None:
    frame = CapturedFrame(
        request_id="request-1",
        device_id="camera-1",
        media_token="opaque-temporary-token",
    )

    assert frame.model_dump() == {
        "request_id": "request-1",
        "device_id": "camera-1",
        "media_token": "opaque-temporary-token",
    }
    with pytest.raises(ValidationError):
        frame.media_token = "another-token"
