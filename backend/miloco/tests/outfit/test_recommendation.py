# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Inventory-only response boundary tests for Outfit recommendations."""

from miloco.outfit.composition import OutfitCandidate
from miloco.outfit.ranking import rank_outfit_candidates
from miloco.outfit.recommendation import build_recommendation_result


def _ranked_options(count: int):
    return rank_outfit_candidates(
        [
            OutfitCandidate(
                item_ids=(f"top-{index}", f"bottom-{index}", f"shoes-{index}"),
                pattern="top_bottom_shoes",
            )
            for index in range(count)
        ]
    )


def test_recommendation_returns_only_first_three_real_ranked_inventory_options():
    result = build_recommendation_result(_ranked_options(4))

    assert result.status == "ready"
    assert [option.candidate.item_ids for option in result.options] == [
        ("top-0", "bottom-0", "shoes-0"),
        ("top-1", "bottom-1", "shoes-1"),
        ("top-2", "bottom-2", "shoes-2"),
    ]
    assert result.message == "Returned three ranked inventory-only outfit options."


def test_recommendation_reports_insufficient_inventory_without_padding_options():
    result = build_recommendation_result(_ranked_options(1))

    assert result.status == "insufficient_inventory"
    assert len(result.options) == 1
    assert result.message == "Need at least two complete inventory-only outfit options."


def test_recommendation_reports_empty_inventory_without_creating_candidates():
    result = build_recommendation_result([])

    assert result.status == "insufficient_inventory"
    assert result.options == ()
