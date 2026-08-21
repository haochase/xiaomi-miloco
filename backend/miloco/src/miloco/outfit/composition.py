# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Inventory-only category-complete Outfit composition."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from miloco.outfit.filtering import OutfitInventoryCandidate
from miloco.outfit.wardrobe import WardrobeCategory

OutfitPattern: TypeAlias = Literal["top_bottom_shoes", "dress_shoes"]


class OutfitCandidate(BaseModel):
    """One category-complete candidate assembled from confirmed inventory only."""

    model_config = ConfigDict(frozen=True)

    item_ids: tuple[str, ...] = Field(min_length=2)
    pattern: OutfitPattern


def compose_outfit_candidates(
    candidates: list[OutfitInventoryCandidate], *, max_options: int = 3
) -> list[OutfitCandidate]:
    """Build at most ``max_options`` complete outfits in input-stable order."""

    if max_options < 1:
        raise ValueError("max_options must be at least 1")

    item_ids_by_category = {
        category: _item_ids_in_category(candidates, category)
        for category in ("top", "bottom", "dress", "shoes")
    }
    outfits: list[OutfitCandidate] = []

    for top_id in item_ids_by_category["top"]:
        for bottom_id in item_ids_by_category["bottom"]:
            for shoe_id in item_ids_by_category["shoes"]:
                outfits.append(
                    OutfitCandidate(
                        item_ids=(top_id, bottom_id, shoe_id),
                        pattern="top_bottom_shoes",
                    )
                )
                if len(outfits) == max_options:
                    return outfits

    for dress_id in item_ids_by_category["dress"]:
        for shoe_id in item_ids_by_category["shoes"]:
            outfits.append(
                OutfitCandidate(
                    item_ids=(dress_id, shoe_id),
                    pattern="dress_shoes",
                )
            )
            if len(outfits) == max_options:
                return outfits

    return outfits


def _item_ids_in_category(
    candidates: list[OutfitInventoryCandidate], category: WardrobeCategory
) -> list[str]:
    return [
        candidate.item.item_id
        for candidate in candidates
        if candidate.item.category == category
    ]
