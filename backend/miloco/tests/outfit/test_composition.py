# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Inventory-only Outfit composition contracts."""

import pytest
from miloco.outfit.composition import compose_outfit_candidates
from miloco.outfit.filtering import OutfitInventoryCandidate
from miloco.outfit.wardrobe import ConfirmedWardrobeItem, WardrobeSourceEvidence


def _candidate(item_id: str, category: str) -> OutfitInventoryCandidate:
    return OutfitInventoryCandidate(
        item=ConfirmedWardrobeItem(
            item_id=item_id,
            owner_person_id="primary-user",
            name=item_id,
            category=category,
            source_evidence=(
                WardrobeSourceEvidence(
                    source_type="manual",
                    reference=f"closet entry {item_id}",
                ),
            ),
            confirmed_at_ms=1,
            confirmed_by_user=True,
        ),
    )


def test_composition_returns_only_complete_inventory_outfits_in_stable_order():
    outfits = compose_outfit_candidates(
        [
            _candidate("navy-top", "top"),
            _candidate("gray-bottom", "bottom"),
            _candidate("white-shoes", "shoes"),
            _candidate("black-dress", "dress"),
        ]
    )

    assert [(outfit.item_ids, outfit.pattern) for outfit in outfits] == [
        (("navy-top", "gray-bottom", "white-shoes"), "top_bottom_shoes"),
        (("black-dress", "white-shoes"), "dress_shoes"),
    ]


def test_composition_limits_inventory_only_options_to_requested_maximum():
    outfits = compose_outfit_candidates(
        [
            _candidate("top-one", "top"),
            _candidate("top-two", "top"),
            _candidate("bottom-one", "bottom"),
            _candidate("bottom-two", "bottom"),
            _candidate("shoes-one", "shoes"),
        ],
        max_options=3,
    )

    assert len(outfits) == 3
    assert all(len(outfit.item_ids) == 3 for outfit in outfits)


def test_composition_returns_no_partial_outfit_and_rejects_invalid_limit():
    assert (
        compose_outfit_candidates(
            [_candidate("navy-top", "top"), _candidate("gray-bottom", "bottom")]
        )
        == []
    )

    with pytest.raises(ValueError, match="max_options"):
        compose_outfit_candidates([], max_options=0)
