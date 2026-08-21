# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Pure, non-mutating comparison of an Outfit recommendation and observation."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from miloco.outfit.ranking import RankedOutfitOption

VisualObservationStatus: TypeAlias = Literal["observed", "uncertain"]
VisualUncertaintyReason: TypeAlias = Literal[
    "low_confidence",
    "unknown_item_id",
    "low_light",
    "occluded",
    "no_person",
    "model_uncertain",
]
TryOnComparisonStatus: TypeAlias = Literal["match", "mismatch", "uncertain"]
TryOnCorrectionStatus: TypeAlias = Literal[
    "no_change",
    "needs_user_review",
    "not_actionable",
]

_OBSERVATION_CONFIDENCE_THRESHOLD = 0.8


class RecommendedOutfitSnapshot(BaseModel):
    """Immutable recommendation facts used for one later visual comparison."""

    model_config = ConfigDict(frozen=True)

    recommendation_id: str = Field(min_length=1)
    owner_person_id: str = Field(min_length=1)
    item_ids: tuple[str, ...] = Field(min_length=1)
    rationale: tuple[str, ...]


class VisualTryOnObservation(BaseModel):
    """Normalized visual evidence bound to one owner and recommendation snapshot."""

    model_config = ConfigDict(frozen=True)

    recommendation_id: str = Field(min_length=1)
    owner_person_id: str = Field(min_length=1)
    observed_item_ids: tuple[str, ...]
    confidence: float = Field(ge=0, le=1)
    status: VisualObservationStatus
    uncertainty_reason: VisualUncertaintyReason | None = None

    @model_validator(mode="after")
    def validate_status_consistency(self) -> VisualTryOnObservation:
        if self.status == "observed" and self.uncertainty_reason is not None:
            raise ValueError("observed observation cannot include uncertainty_reason")
        if self.status == "uncertain" and self.uncertainty_reason is None:
            raise ValueError("uncertain observation requires uncertainty_reason")
        return self


class TryOnComparison(BaseModel):
    """Read-only difference between a recommendation snapshot and visual evidence."""

    model_config = ConfigDict(frozen=True)

    status: TryOnComparisonStatus
    missing_item_ids: tuple[str, ...] = ()
    unexpected_item_ids: tuple[str, ...] = ()


class TryOnCorrection(BaseModel):
    """A user-review prompt that never mutates Outfit facts."""

    model_config = ConfigDict(frozen=True)

    status: TryOnCorrectionStatus
    requires_user_confirmation: bool
    missing_item_ids: tuple[str, ...] = ()
    unexpected_item_ids: tuple[str, ...] = ()


def snapshot_recommended_outfit(
    *,
    recommendation_id: str,
    owner_person_id: str,
    option: RankedOutfitOption,
) -> RecommendedOutfitSnapshot:
    """Capture one selected option without altering its recommendation or inventory."""

    return RecommendedOutfitSnapshot(
        recommendation_id=recommendation_id,
        owner_person_id=owner_person_id,
        item_ids=option.candidate.item_ids,
        rationale=option.rationale,
    )


def normalize_visual_observation(
    *,
    snapshot: RecommendedOutfitSnapshot,
    observed_item_ids: tuple[str, ...],
    confidence: float,
    status: VisualObservationStatus = "observed",
    uncertainty_reason: VisualUncertaintyReason | None = None,
) -> VisualTryOnObservation:
    """Normalize candidate-scoped evidence without inferring identity outside the snapshot."""

    normalized_item_ids = tuple(item_id.strip() for item_id in observed_item_ids)
    if status == "uncertain" or uncertainty_reason is not None:
        return _uncertain_observation(
            snapshot=snapshot,
            observed_item_ids=normalized_item_ids,
            confidence=confidence,
            reason=uncertainty_reason or "low_confidence",
        )
    if confidence < _OBSERVATION_CONFIDENCE_THRESHOLD:
        return _uncertain_observation(
            snapshot=snapshot,
            observed_item_ids=normalized_item_ids,
            confidence=confidence,
            reason="low_confidence",
        )
    if any(item_id not in snapshot.item_ids for item_id in normalized_item_ids):
        return _uncertain_observation(
            snapshot=snapshot,
            observed_item_ids=normalized_item_ids,
            confidence=confidence,
            reason="unknown_item_id",
        )
    return VisualTryOnObservation(
        recommendation_id=snapshot.recommendation_id,
        owner_person_id=snapshot.owner_person_id,
        observed_item_ids=normalized_item_ids,
        confidence=confidence,
        status="observed",
    )


def compare_snapshot_to_observation(
    snapshot: RecommendedOutfitSnapshot,
    observation: VisualTryOnObservation,
) -> TryOnComparison:
    """Compare only matching snapshot evidence and retain uncertainty conservatively."""

    if (
        snapshot.recommendation_id != observation.recommendation_id
        or snapshot.owner_person_id != observation.owner_person_id
    ):
        raise ValueError("snapshot and observation must share recommendation and owner")
    if observation.status == "uncertain" or any(
        item_id not in snapshot.item_ids for item_id in observation.observed_item_ids
    ):
        return TryOnComparison(status="uncertain")

    observed_item_ids = set(observation.observed_item_ids)
    missing_item_ids = tuple(
        item_id for item_id in snapshot.item_ids if item_id not in observed_item_ids
    )
    if missing_item_ids:
        return TryOnComparison(
            status="mismatch",
            missing_item_ids=missing_item_ids,
        )
    return TryOnComparison(status="match")


def build_try_on_correction(comparison: TryOnComparison) -> TryOnCorrection:
    """Return an explicit review state without applying a recommendation correction."""

    if comparison.status == "match":
        return TryOnCorrection(
            status="no_change",
            requires_user_confirmation=False,
        )
    if comparison.status == "mismatch":
        return TryOnCorrection(
            status="needs_user_review",
            requires_user_confirmation=True,
            missing_item_ids=comparison.missing_item_ids,
            unexpected_item_ids=comparison.unexpected_item_ids,
        )
    return TryOnCorrection(
        status="not_actionable",
        requires_user_confirmation=True,
    )


def _uncertain_observation(
    *,
    snapshot: RecommendedOutfitSnapshot,
    observed_item_ids: tuple[str, ...],
    confidence: float,
    reason: VisualUncertaintyReason,
) -> VisualTryOnObservation:
    return VisualTryOnObservation(
        recommendation_id=snapshot.recommendation_id,
        owner_person_id=snapshot.owner_person_id,
        observed_item_ids=observed_item_ids,
        confidence=confidence,
        status="uncertain",
        uncertainty_reason=reason,
    )
