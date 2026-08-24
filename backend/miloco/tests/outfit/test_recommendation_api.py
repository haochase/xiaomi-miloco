# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Contracts for request-safe Outfit recommendation snapshots."""

import pytest
from miloco.outfit.ranking import RankedOutfitOption
from miloco.outfit.recommendation import OutfitRecommendationResult
from miloco.outfit.recommendation_api import (
    CreateRecommendationRequest,
    RecommendationApiProblem,
    RecommendationSnapshot,
    snapshot_from_result,
)
from pydantic import ValidationError


def _option(*item_ids: str) -> RankedOutfitOption:
    return RankedOutfitOption.model_validate(
        {
            "candidate": {
                "item_ids": item_ids,
                "pattern": "top_bottom_shoes",
            },
            "score": 100,
            "score_components": [
                {
                    "name": "inventory_complete",
                    "value": 100,
                    "explanation": "inventory complete",
                }
            ],
            "rationale": ["uses confirmed inventory"],
        }
    )


def test_recommendation_request_rejects_owner_selector() -> None:
    with pytest.raises(ValidationError):
        CreateRecommendationRequest.model_validate(
            {
                "occasion": "commute",
                "owner_person_id": "another-person",
            }
        )


def test_recommendation_problem_covers_context_and_sparse_inventory() -> None:
    assert RecommendationApiProblem(
        code="recommendation_needs_context",
    ).model_dump() == {"code": "recommendation_needs_context"}
    assert (
        RecommendationApiProblem(
            code="recommendation_insufficient_inventory",
        ).code
        == "recommendation_insufficient_inventory"
    )
    with pytest.raises(ValidationError):
        RecommendationApiProblem.model_validate(
            {
                "code": "recommendation_needs_context",
                "message": "E:\\private-media\\unsafe",
            }
        )


def test_snapshot_preserves_only_bounded_candidate_item_ids() -> None:
    result = OutfitRecommendationResult(
        status="ready",
        options=(
            _option("item-top", "item-bottom", "item-shoes"),
            _option("item-dress", "item-shoes"),
        ),
        message="internal ranking explanation",
    )

    snapshot = snapshot_from_result(
        snapshot_id="rec-1",
        context=CreateRecommendationRequest(occasion="commute").to_context(),
        result=result,
        created_at_ms=100,
        ranking_version="deterministic-v1",
    )

    assert snapshot.model_dump() == {
        "snapshot_id": "rec-1",
        "context": {"occasion": "commute", "activity": None, "day_kind": "unknown"},
        "status": "ready",
        "option_item_ids": (
            ("item-top", "item-bottom", "item-shoes"),
            ("item-dress", "item-shoes"),
        ),
        "ranking_version": "deterministic-v1",
        "created_at_ms": 100,
    }


def test_snapshot_rejects_more_than_three_options() -> None:
    with pytest.raises(ValidationError):
        RecommendationSnapshot.model_validate(
            {
                "snapshot_id": "rec-1",
                "context": {"occasion": "commute"},
                "status": "ready",
                "option_item_ids": [
                    ["item-1"],
                    ["item-2"],
                    ["item-3"],
                    ["item-4"],
                ],
                "ranking_version": "deterministic-v1",
                "created_at_ms": 100,
            }
        )


@pytest.mark.parametrize(
    ("status", "option_item_ids"),
    [
        ("ready", []),
        ("ready", [["item-1", "item-2"]]),
        (
            "insufficient_inventory",
            [["item-1", "item-2"], ["item-3", "item-4"]],
        ),
    ],
)
def test_snapshot_rejects_status_and_candidate_count_mismatches(
    status: str,
    option_item_ids: list[list[str]],
) -> None:
    with pytest.raises(ValidationError):
        RecommendationSnapshot.model_validate(
            {
                "snapshot_id": "rec-1",
                "context": {"occasion": "commute"},
                "status": status,
                "option_item_ids": option_item_ids,
                "ranking_version": "deterministic-v1",
                "created_at_ms": 100,
            }
        )


def test_snapshot_is_immutable_and_rejects_empty_candidate_ids() -> None:
    snapshot = RecommendationSnapshot.model_validate(
        {
            "snapshot_id": "rec-1",
            "context": {"activity": "walk"},
            "status": "insufficient_inventory",
            "option_item_ids": [["item-1", "item-2"]],
            "ranking_version": "deterministic-v1",
            "created_at_ms": 100,
        }
    )

    with pytest.raises(ValidationError):
        RecommendationSnapshot.model_validate(
            {
                **snapshot.model_dump(),
                "option_item_ids": [["item-1", "  "]],
            }
        )
    with pytest.raises(ValidationError):
        RecommendationSnapshot.model_validate(
            {
                **snapshot.model_dump(),
                "snapshot_id": "E:\\private-media\\unsafe",
            }
        )
    with pytest.raises(ValidationError):
        snapshot.snapshot_id = "rec-2"
