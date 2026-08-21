# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Stable, explainable fallback ranking for category-complete Outfit candidates."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict

from miloco.outfit.composition import OutfitCandidate

RankingComponentName: TypeAlias = Literal["inventory_complete", "stable_fallback"]


class RankingScoreComponent(BaseModel):
    """One deterministic contribution to a ranked Outfit option."""

    model_config = ConfigDict(frozen=True)

    name: RankingComponentName
    value: int
    explanation: str


class RankedOutfitOption(BaseModel):
    """An inventory-only candidate with an inspectable deterministic score."""

    model_config = ConfigDict(frozen=True)

    candidate: OutfitCandidate
    score: int
    score_components: tuple[RankingScoreComponent, ...]
    rationale: tuple[str, ...]


def rank_outfit_candidates(
    candidates: list[OutfitCandidate],
) -> list[RankedOutfitOption]:
    """Rank complete candidates without inventing preference or inventory facts.

    Current candidates have equal deterministic scores because preference learning is
    confirmation-gated and arrives in a later milestone. Python's stable ordering
    preserves the already deterministic composition order for equal scores.
    """

    return [
        RankedOutfitOption(
            candidate=candidate,
            score=100,
            score_components=(
                RankingScoreComponent(
                    name="inventory_complete",
                    value=100,
                    explanation=(
                        "Candidate contains a category-complete outfit from filtered "
                        "inventory."
                    ),
                ),
                RankingScoreComponent(
                    name="stable_fallback",
                    value=0,
                    explanation=(
                        "No confirmed preference signal is available; composition order "
                        "breaks ties."
                    ),
                ),
            ),
            rationale=(
                "Uses only hard-filtered confirmed inventory.",
                "No confirmed preference score is available; retained stable composition order.",
            ),
        )
        for candidate in candidates
    ]
