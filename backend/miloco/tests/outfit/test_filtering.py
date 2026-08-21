# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Hard-filter contracts for confirmed Outfit inventory."""

from miloco.outfit.filtering import (
    OutfitInventoryCandidate,
    WeatherRequirement,
    filter_inventory_candidates,
)
from miloco.outfit.wardrobe import ConfirmedWardrobeItem, WardrobeSourceEvidence


def _candidate(
    item_id: str,
    *,
    availability: str = "available",
    weather_capabilities: tuple[str, ...] = (),
) -> OutfitInventoryCandidate:
    return OutfitInventoryCandidate(
        item=ConfirmedWardrobeItem(
            item_id=item_id,
            owner_person_id="primary-user",
            name=item_id,
            category="outerwear",
            source_evidence=(
                WardrobeSourceEvidence(
                    source_type="manual",
                    reference=f"closet entry {item_id}",
                ),
            ),
            confirmed_at_ms=1,
            confirmed_by_user=True,
            availability=availability,
        ),
        weather_capabilities=weather_capabilities,
    )


def test_rain_requirement_keeps_only_available_rain_ready_inventory():
    candidates = [
        _candidate("rain-jacket", weather_capabilities=("rain_ready",)),
        _candidate("wool-coat"),
        _candidate(
            "laundry-rain-jacket",
            availability="laundry",
            weather_capabilities=("rain_ready",),
        ),
    ]

    filtered = filter_inventory_candidates(
        candidates,
        weather=WeatherRequirement(condition="rain"),
    )

    assert [candidate.item.item_id for candidate in filtered] == ["rain-jacket"]


def test_non_rain_requirement_keeps_all_available_confirmed_inventory():
    candidates = [
        _candidate("wool-coat"),
        _candidate("laundry-shirt", availability="laundry"),
    ]

    filtered = filter_inventory_candidates(
        candidates,
        weather=WeatherRequirement(condition="clear"),
    )

    assert [candidate.item.item_id for candidate in filtered] == ["wool-coat"]


def test_missing_weather_keeps_available_confirmed_inventory():
    filtered = filter_inventory_candidates(
        [_candidate("wool-coat"), _candidate("retired-coat", availability="retired")],
        weather=None,
    )

    assert [candidate.item.item_id for candidate in filtered] == ["wool-coat"]
