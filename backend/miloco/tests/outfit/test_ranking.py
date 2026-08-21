# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Deterministic, explainable ranking contracts for Outfit candidates."""

from miloco.outfit.composition import OutfitCandidate
from miloco.outfit.ranking import rank_outfit_candidates


def test_ranking_keeps_composition_order_when_all_candidates_have_equal_scores():
    candidates = [
        OutfitCandidate(
            item_ids=("navy-top", "gray-bottom", "white-shoes"),
            pattern="top_bottom_shoes",
        ),
        OutfitCandidate(
            item_ids=("black-dress", "white-shoes"),
            pattern="dress_shoes",
        ),
    ]

    ranked = rank_outfit_candidates(candidates)

    assert [option.candidate for option in ranked] == candidates
    assert [option.score for option in ranked] == [100, 100]


def test_ranking_exposes_only_deterministic_inventory_score_components():
    ranked = rank_outfit_candidates(
        [
            OutfitCandidate(
                item_ids=("black-dress", "white-shoes"),
                pattern="dress_shoes",
            )
        ]
    )

    assert [
        (component.name, component.value, component.explanation)
        for component in ranked[0].score_components
    ] == [
        (
            "inventory_complete",
            100,
            "Candidate contains a category-complete outfit from filtered inventory.",
        ),
        (
            "stable_fallback",
            0,
            "No confirmed preference signal is available; composition order breaks ties.",
        ),
    ]
    assert ranked[0].rationale == (
        "Uses only hard-filtered confirmed inventory.",
        "No confirmed preference score is available; retained stable composition order.",
    )


def test_ranking_does_not_mutate_candidate_input_or_invent_outfit_items():
    candidate = OutfitCandidate(
        item_ids=("navy-top", "gray-bottom", "white-shoes"),
        pattern="top_bottom_shoes",
    )

    ranked = rank_outfit_candidates([candidate])

    assert ranked[0].candidate is candidate
    assert ranked[0].candidate.item_ids == (
        "navy-top",
        "gray-bottom",
        "white-shoes",
    )
