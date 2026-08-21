# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Honest response boundary for deterministic Outfit recommendation options."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from miloco.outfit.ranking import RankedOutfitOption

RecommendationStatus: TypeAlias = Literal["ready", "insufficient_inventory"]


class OutfitRecommendationResult(BaseModel):
    """Expose up to three ranked, inventory-only options without padding sparse data."""

    model_config = ConfigDict(frozen=True)

    status: RecommendationStatus
    options: tuple[RankedOutfitOption, ...] = Field(max_length=3)
    message: str


def build_recommendation_result(
    ranked_options: list[RankedOutfitOption],
) -> OutfitRecommendationResult:
    """Return real ranked options and surface sparse inventory instead of fabricating one."""

    options = tuple(ranked_options[:3])
    if len(options) < 2:
        return OutfitRecommendationResult(
            status="insufficient_inventory",
            options=options,
            message="Need at least two complete inventory-only outfit options.",
        )

    option_count = "two" if len(options) == 2 else "three"
    return OutfitRecommendationResult(
        status="ready",
        options=options,
        message=f"Returned {option_count} ranked inventory-only outfit options.",
    )
