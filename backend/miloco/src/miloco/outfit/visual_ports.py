# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Narrow async ports for explicit, temporary Outfit visual review."""

from __future__ import annotations

from typing import Literal, Protocol, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from miloco.outfit.visual_observability import VisualReviewAuditRecord

VisionProviderObservationStatus: TypeAlias = Literal["observed", "uncertain"]
VisionProviderUncertaintyReason: TypeAlias = Literal[
    "low_light",
    "occluded",
    "no_person",
    "model_uncertain",
]


class CapturedFrame(BaseModel):
    """An opaque reference to one temporary frame captured after an explicit trigger."""

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    media_token: str = Field(min_length=1)


class VisionCandidateItem(BaseModel):
    """The minimum recommendation-scoped fact visible to a vision provider."""

    model_config = ConfigDict(frozen=True)

    item_id: str = Field(min_length=1)
    description: str = Field(min_length=1, max_length=512)


class VisionProviderUsage(BaseModel):
    """Finite provider-reported usage for one bounded observation call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int = Field(ge=0, strict=True)
    output_tokens: int = Field(ge=0, strict=True)
    video_tokens: int = Field(ge=0, strict=True)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.video_tokens


class VisionProviderRejected(ValueError):
    """Sanitized provider rejection that preserves already-reported usage."""

    def __init__(
        self,
        *,
        usage: VisionProviderUsage | None,
        error_code: str = "provider_rejected",
    ) -> None:
        self.usage = usage
        super().__init__(error_code)


class VisionProviderObservation(BaseModel):
    """Raw structured evidence returned by a constrained vision provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observed_item_ids: tuple[str, ...]
    confidence: float = Field(ge=0, le=1)
    status: VisionProviderObservationStatus = "observed"
    uncertainty_reason: VisionProviderUncertaintyReason | None = None
    usage: VisionProviderUsage

    @model_validator(mode="after")
    def validate_status_consistency(self) -> VisionProviderObservation:
        if self.status == "observed" and self.uncertainty_reason is not None:
            raise ValueError("observed observation cannot include uncertainty_reason")
        if self.status == "uncertain" and self.uncertainty_reason is None:
            raise ValueError("uncertain observation requires uncertainty_reason")
        return self


class FrameCapturePort(Protocol):
    """Host-owned one-frame capture capability with no continuous-monitoring API."""

    async def capture_frame(
        self, *, device_id: str, request_id: str
    ) -> CapturedFrame: ...


class OutfitVisionProvider(Protocol):
    """Provider restricted to one frame and current recommendation candidates.

    Implementations must cooperate with cancellation promptly and must not retain the frame,
    its opaque media token, or candidate context after ``observe`` returns or raises.
    """

    async def observe(
        self,
        *,
        frame: CapturedFrame,
        candidate_items: tuple[VisionCandidateItem, ...],
        max_tokens: int,
    ) -> VisionProviderObservation: ...


class TemporaryMediaStore(Protocol):
    """Host-owned cleanup port for every captured temporary frame.

    Deletion must be idempotent, cooperate with cancellation, and eventually finish even when
    the caller has already returned a conservative cleanup-failed outcome.
    """

    async def delete_frame(self, *, frame: CapturedFrame) -> None: ...


class CleanupAuditPort(Protocol):
    """Host-owned warning sink that receives no paths, media or provider errors."""

    async def record_cleanup_failure(
        self,
        *,
        request_id: str,
        device_id: str,
        error_code: str,
    ) -> None: ...


class VisualReviewAuditPort(Protocol):
    """Host-owned low-sensitivity sink for one terminal visual-review record."""

    async def record_visual_review(self, record: VisualReviewAuditRecord) -> None: ...
