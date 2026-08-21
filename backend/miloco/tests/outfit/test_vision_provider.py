# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Schema contracts for constrained Outfit vision-provider outputs."""

import pytest
from miloco.outfit.vision_provider import (
    NormalizedVisionProviderObservation,
    VisionProviderPayloadRejected,
    parse_vision_provider_payload,
)
from miloco.outfit.visual_ports import VisionCandidateItem, VisionProviderObservation
from pydantic import ValidationError


def _candidates() -> tuple[VisionCandidateItem, ...]:
    return (
        VisionCandidateItem(item_id="navy-top", description="navy top"),
        VisionCandidateItem(item_id="gray-bottom", description="gray bottom"),
        VisionCandidateItem(item_id="white-shoes", description="white shoes"),
    )


def _usage() -> dict[str, int]:
    return {"input_tokens": 12, "output_tokens": 3, "video_tokens": 5}


def test_provider_payload_accepts_only_current_candidate_ids_with_typed_evidence() -> (
    None
):
    observation = parse_vision_provider_payload(
        {
            "status": "observed",
            "observed_item_ids": ["navy-top", "gray-bottom", "white-shoes"],
            "confidence": 0.92,
            "usage": _usage(),
        },
        candidate_items=_candidates(),
    )

    assert observation.status == "observed"
    assert observation.observed_item_ids == (
        "navy-top",
        "gray-bottom",
        "white-shoes",
    )
    assert observation.confidence == 0.92
    assert observation.uncertainty_reason is None


def test_provider_payload_rejects_unknown_item_without_coercing_wardrobe_facts() -> (
    None
):
    with pytest.raises(VisionProviderPayloadRejected) as caught:
        parse_vision_provider_payload(
            {
                "status": "observed",
                "observed_item_ids": ["navy-top", "black-shoes"],
                "confidence": 0.92,
                "usage": _usage(),
            },
            candidate_items=_candidates(),
        )
    assert caught.value.reason == "unknown_candidate_item"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "status": "observed",
            "observed_item_ids": ["private-unknown-item"],
            "confidence": 0.92,
            "usage": _usage(),
        },
        {
            "status": "observed",
            "observed_item_ids": ["navy-top"],
            "confidence": 0.92,
            "uncertainty_reason": "low_light",
            "usage": _usage(),
        },
    ],
)
def test_semantic_provider_rejection_carries_usage_without_leaking_details(
    payload: dict[str, object],
) -> None:
    with pytest.raises(VisionProviderPayloadRejected) as caught:
        parse_vision_provider_payload(payload, candidate_items=_candidates())

    assert caught.value.usage.total_tokens == 20
    assert str(caught.value) == "provider_payload_rejected"
    assert "private-unknown-item" not in str(caught.value)


@pytest.mark.parametrize(
    "reason", ["low_light", "occluded", "no_person", "model_uncertain"]
)
def test_provider_uncertainty_requires_a_known_conservative_reason(reason: str) -> None:
    observation = parse_vision_provider_payload(
        {
            "status": "uncertain",
            "observed_item_ids": [],
            "confidence": 0.0,
            "uncertainty_reason": reason,
            "usage": _usage(),
        },
        candidate_items=_candidates(),
    )

    assert observation.status == "uncertain"
    assert observation.uncertainty_reason == reason


def test_provider_payload_rejects_extra_fields_and_missing_uncertainty_reason() -> None:
    with pytest.raises(VisionProviderPayloadRejected) as invalid_schema:
        parse_vision_provider_payload(
            {
                "status": "observed",
                "observed_item_ids": ["navy-top"],
                "confidence": 0.92,
                "unreviewed_explanation": "not accepted",
                "usage": _usage(),
            },
            candidate_items=_candidates(),
        )
    assert invalid_schema.value.reason == "invalid_schema"
    with pytest.raises(VisionProviderPayloadRejected) as missing_reason:
        parse_vision_provider_payload(
            {
                "status": "uncertain",
                "observed_item_ids": [],
                "confidence": 0.0,
                "usage": _usage(),
            },
            candidate_items=_candidates(),
        )
    assert missing_reason.value.reason == "uncertainty_reason_required"


class _FakePayloadPort:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.max_tokens_seen: list[int | None] = []

    async def observe_payload(
        self,
        *,
        media_token: str,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            (media_token, tuple(item.item_id for item in candidate_items))
        )
        self.max_tokens_seen.append(max_tokens)
        return self.payload


@pytest.mark.asyncio
async def test_constrained_provider_adapter_returns_only_visual_port_observation() -> (
    None
):
    from miloco.outfit.vision_provider import ConstrainedVisionProviderAdapter
    from miloco.outfit.visual_ports import CapturedFrame

    payload_port = _FakePayloadPort(
        {
            "status": "observed",
            "observed_item_ids": ["navy-top"],
            "confidence": 0.91,
            "usage": _usage(),
        }
    )
    adapter = ConstrainedVisionProviderAdapter(payload_port=payload_port)

    observation = await adapter.observe(
        frame=CapturedFrame(
            request_id="request-1",
            device_id="camera-1",
            media_token="opaque-token",
        ),
        candidate_items=_candidates(),
        max_tokens=20,
    )

    assert observation.observed_item_ids == ("navy-top",)
    assert observation.confidence == 0.91
    assert payload_port.calls == [
        ("opaque-token", ("navy-top", "gray-bottom", "white-shoes"))
    ]


@pytest.mark.asyncio
async def test_constrained_provider_adapter_rejects_invalid_payload_before_service_output() -> (
    None
):
    from miloco.outfit.vision_provider import (
        ConstrainedVisionProviderAdapter,
        VisionProviderPayloadRejected,
    )
    from miloco.outfit.visual_ports import CapturedFrame

    adapter = ConstrainedVisionProviderAdapter(
        payload_port=_FakePayloadPort(
            {
                "status": "observed",
                "observed_item_ids": ["not-a-candidate"],
                "confidence": 0.91,
                "usage": _usage(),
            }
        )
    )

    with pytest.raises(VisionProviderPayloadRejected) as caught:
        await adapter.observe(
            frame=CapturedFrame(
                request_id="request-1",
                device_id="camera-1",
                media_token="opaque-token",
            ),
            candidate_items=_candidates(),
            max_tokens=20,
        )
    assert caught.value.reason == "unknown_candidate_item"


@pytest.mark.asyncio
async def test_constrained_provider_adapter_preserves_conservative_uncertainty() -> (
    None
):
    from miloco.outfit.vision_provider import ConstrainedVisionProviderAdapter
    from miloco.outfit.visual_ports import CapturedFrame

    adapter = ConstrainedVisionProviderAdapter(
        payload_port=_FakePayloadPort(
            {
                "status": "uncertain",
                "observed_item_ids": [],
                "confidence": 0.95,
                "uncertainty_reason": "low_light",
                "usage": _usage(),
            }
        )
    )

    observation = await adapter.observe(
        frame=CapturedFrame(
            request_id="request-1",
            device_id="camera-1",
            media_token="opaque-token",
        ),
        candidate_items=_candidates(),
        max_tokens=20,
    )

    assert observation.status == "uncertain"
    assert observation.uncertainty_reason == "low_light"


def test_raw_provider_observation_rejects_observed_uncertainty_contradiction() -> None:
    with pytest.raises(ValidationError, match="observed.*uncertainty"):
        VisionProviderObservation(
            observed_item_ids=("navy-top",),
            confidence=0.99,
            status="observed",
            uncertainty_reason="occluded",
            usage=_usage(),
        )


def test_normalized_provider_observation_rejects_observed_uncertainty() -> None:
    with pytest.raises(ValidationError, match="observed.*uncertainty"):
        NormalizedVisionProviderObservation(
            observed_item_ids=("navy-top",),
            confidence=0.99,
            status="observed",
            uncertainty_reason="low_light",
            usage=_usage(),
        )


@pytest.mark.asyncio
async def test_provider_receives_hard_token_budget_and_returns_actual_usage() -> None:
    from miloco.outfit.vision_provider import ConstrainedVisionProviderAdapter
    from miloco.outfit.visual_ports import CapturedFrame

    payload_port = _FakePayloadPort(
        {
            "status": "observed",
            "observed_item_ids": ["navy-top"],
            "confidence": 0.91,
            "usage": {
                "input_tokens": 12,
                "output_tokens": 3,
                "video_tokens": 5,
            },
        }
    )
    adapter = ConstrainedVisionProviderAdapter(payload_port=payload_port)

    observation = await adapter.observe(
        frame=CapturedFrame(
            request_id="request-1",
            device_id="camera-1",
            media_token="opaque-token",
        ),
        candidate_items=_candidates(),
        max_tokens=20,
    )

    assert payload_port.max_tokens_seen == [20]
    assert observation.usage.input_tokens == 12
    assert observation.usage.output_tokens == 3
    assert observation.usage.video_tokens == 5
    assert observation.usage.total_tokens == 20
