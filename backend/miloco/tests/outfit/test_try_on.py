# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Pure, non-mutating contracts for Outfit try-on comparison."""

import pytest
from miloco.outfit.composition import OutfitCandidate
from miloco.outfit.ranking import rank_outfit_candidates
from miloco.outfit.try_on import (
    TryOnComparison,
    VisualTryOnObservation,
    build_try_on_correction,
    compare_snapshot_to_observation,
    normalize_visual_observation,
    snapshot_recommended_outfit,
)
from pydantic import ValidationError


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


def test_snapshot_is_immutable_and_retains_only_selected_recommendation_facts() -> None:
    snapshot = _snapshot()

    assert snapshot.item_ids == ("navy-top", "gray-bottom", "white-shoes")
    assert snapshot.owner_person_id == "primary-person"
    assert snapshot.rationale == (
        "Uses only hard-filtered confirmed inventory.",
        "No confirmed preference score is available; retained stable composition order.",
    )
    with pytest.raises(ValidationError):
        snapshot.item_ids = ("other-item",)


def test_low_confidence_observation_is_uncertain_and_never_infers_mismatch() -> None:
    snapshot = _snapshot()
    observation = normalize_visual_observation(
        snapshot=snapshot,
        observed_item_ids=("navy-top",),
        confidence=0.49,
    )

    comparison = compare_snapshot_to_observation(snapshot, observation)

    assert observation.status == "uncertain"
    assert observation.uncertainty_reason == "low_confidence"
    assert comparison == TryOnComparison(status="uncertain")
    assert build_try_on_correction(comparison).status == "not_actionable"


def test_unknown_item_id_is_uncertain_not_a_wardrobe_or_recommendation_mutation() -> (
    None
):
    snapshot = _snapshot()
    observation = normalize_visual_observation(
        snapshot=snapshot,
        observed_item_ids=("navy-top", "black-shoes"),
        confidence=0.95,
    )

    comparison = compare_snapshot_to_observation(snapshot, observation)

    assert observation.status == "uncertain"
    assert observation.uncertainty_reason == "unknown_item_id"
    assert comparison == TryOnComparison(status="uncertain")
    correction = build_try_on_correction(comparison)
    assert correction.requires_user_confirmation is True
    assert correction.missing_item_ids == ()
    assert correction.unexpected_item_ids == ()


def test_high_confidence_missing_selected_item_requires_user_review_without_mutation() -> (
    None
):
    snapshot = _snapshot()
    observation = normalize_visual_observation(
        snapshot=snapshot,
        observed_item_ids=("navy-top", "gray-bottom"),
        confidence=0.95,
    )

    comparison = compare_snapshot_to_observation(snapshot, observation)
    correction = build_try_on_correction(comparison)

    assert comparison.status == "mismatch"
    assert comparison.missing_item_ids == ("white-shoes",)
    assert comparison.unexpected_item_ids == ()
    assert correction.status == "needs_user_review"
    assert correction.requires_user_confirmation is True
    assert correction.missing_item_ids == ("white-shoes",)


def test_comparison_rejects_snapshot_owner_or_recommendation_mismatch() -> None:
    snapshot = _snapshot()
    observation = normalize_visual_observation(
        snapshot=snapshot,
        observed_item_ids=snapshot.item_ids,
        confidence=0.95,
    ).model_copy(update={"owner_person_id": "another-person"})

    with pytest.raises(ValueError, match="recommendation and owner"):
        compare_snapshot_to_observation(snapshot, observation)


@pytest.mark.parametrize("reason", ["low_light", "occluded"])
def test_observed_environmental_uncertainty_is_normalized_as_non_actionable(
    reason: str,
) -> None:
    snapshot = _snapshot()

    observation = normalize_visual_observation(
        snapshot=snapshot,
        observed_item_ids=snapshot.item_ids,
        confidence=0.99,
        status="observed",
        uncertainty_reason=reason,
    )

    assert observation.status == "uncertain"
    assert observation.uncertainty_reason == reason
    assert compare_snapshot_to_observation(snapshot, observation).status == "uncertain"


def test_normalized_observation_model_rejects_observed_uncertainty_contradiction() -> (
    None
):
    with pytest.raises(ValidationError, match="observed.*uncertainty"):
        VisualTryOnObservation(
            recommendation_id="recommendation-1",
            owner_person_id="primary-person",
            observed_item_ids=("navy-top",),
            confidence=0.99,
            status="observed",
            uncertainty_reason="low_light",
        )
