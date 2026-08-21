# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Strict, candidate-scoped schema for future Outfit vision-provider responses."""

from __future__ import annotations

from typing import Any, Literal, Protocol, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from miloco.outfit.visual_ports import (
    CapturedFrame,
    OutfitVisionProvider,
    VisionCandidateItem,
    VisionProviderObservation,
    VisionProviderRejected,
    VisionProviderUsage,
)

ProviderObservationStatus: TypeAlias = Literal["observed", "uncertain"]
ProviderUncertaintyReason: TypeAlias = Literal[
    "low_light",
    "occluded",
    "no_person",
    "model_uncertain",
]


class VisionProviderPayloadRejected(VisionProviderRejected):
    """A provider response could not become constrained Outfit evidence."""

    def __init__(
        self,
        reason: str,
        *,
        usage: VisionProviderUsage | None = None,
    ) -> None:
        self.reason = reason
        super().__init__(
            usage=usage,
            error_code="provider_payload_rejected",
        )


class NormalizedVisionProviderObservation(BaseModel):
    """Candidate-scoped, typed provider evidence with no free-form explanation."""

    model_config = ConfigDict(frozen=True)

    status: ProviderObservationStatus
    observed_item_ids: tuple[str, ...]
    confidence: float = Field(ge=0, le=1)
    uncertainty_reason: ProviderUncertaintyReason | None = None
    usage: VisionProviderUsage

    @model_validator(mode="after")
    def validate_status_consistency(self) -> NormalizedVisionProviderObservation:
        if self.status == "observed" and self.uncertainty_reason is not None:
            raise ValueError("observed observation cannot include uncertainty_reason")
        if self.status == "uncertain" and self.uncertainty_reason is None:
            raise ValueError("uncertain observation requires uncertainty_reason")
        return self


class _VisionProviderPayload(BaseModel):
    """The only JSON shape accepted from a future vision-provider adapter."""

    model_config = ConfigDict(extra="forbid")

    status: ProviderObservationStatus
    observed_item_ids: tuple[str, ...]
    confidence: float = Field(ge=0, le=1)
    uncertainty_reason: ProviderUncertaintyReason | None = None
    usage: VisionProviderUsage


class VisionPayloadPort(Protocol):
    """Host-injected payload source; it may be backed by a future model adapter."""

    async def observe_payload(
        self,
        *,
        media_token: str,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> dict[str, Any]: ...


class ConstrainedVisionProviderAdapter(OutfitVisionProvider):
    """Convert one host payload into the existing narrow provider observation port."""

    def __init__(self, *, payload_port: VisionPayloadPort) -> None:
        self._payload_port = payload_port

    async def observe(
        self,
        *,
        frame: CapturedFrame,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> VisionProviderObservation:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        parsed = parse_vision_provider_payload(
            await self._payload_port.observe_payload(
                media_token=frame.media_token,
                candidate_items=candidate_items,
                max_tokens=max_tokens,
            ),
            candidate_items=candidate_items,
        )
        return VisionProviderObservation(
            observed_item_ids=parsed.observed_item_ids,
            confidence=parsed.confidence,
            status=parsed.status,
            uncertainty_reason=parsed.uncertainty_reason,
            usage=parsed.usage,
        )


def parse_vision_provider_payload(
    payload: dict[str, Any],
    *,
    candidate_items: tuple[VisionCandidateItem, ...],
) -> NormalizedVisionProviderObservation:
    """Accept strict candidate evidence or reject it without mutating Outfit facts."""

    usage = _payload_usage(payload)
    try:
        parsed = _VisionProviderPayload.model_validate(payload)
    except ValidationError as exc:
        raise VisionProviderPayloadRejected(
            "invalid_schema",
            usage=usage,
        ) from exc

    candidate_ids = {candidate.item_id for candidate in candidate_items}
    if any(item_id not in candidate_ids for item_id in parsed.observed_item_ids):
        raise VisionProviderPayloadRejected(
            "unknown_candidate_item",
            usage=parsed.usage,
        )
    if parsed.status == "uncertain" and parsed.uncertainty_reason is None:
        raise VisionProviderPayloadRejected(
            "uncertainty_reason_required",
            usage=parsed.usage,
        )
    if parsed.status == "observed" and parsed.uncertainty_reason is not None:
        raise VisionProviderPayloadRejected(
            "observed_cannot_include_uncertainty_reason",
            usage=parsed.usage,
        )

    return NormalizedVisionProviderObservation(
        status=parsed.status,
        observed_item_ids=parsed.observed_item_ids,
        confidence=parsed.confidence,
        uncertainty_reason=parsed.uncertainty_reason,
        usage=parsed.usage,
    )


def _payload_usage(payload: dict[str, Any]) -> VisionProviderUsage | None:
    try:
        return VisionProviderUsage.model_validate(payload.get("usage"))
    except ValidationError:
        return None
