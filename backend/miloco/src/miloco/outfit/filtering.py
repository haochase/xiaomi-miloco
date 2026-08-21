# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Deterministic hard filters for confirmed Outfit inventory."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from miloco.outfit.wardrobe import ConfirmedWardrobeItem

WeatherCapability: TypeAlias = Literal["rain_ready"]


class WeatherRequirement(BaseModel):
    """A resolved weather fact supplied by a future host-owned weather port."""

    model_config = ConfigDict(frozen=True)

    condition: str


class OutfitInventoryCandidate(BaseModel):
    """A confirmed item plus explicit capabilities used by hard filtering."""

    model_config = ConfigDict(frozen=True)

    item: ConfirmedWardrobeItem
    weather_capabilities: tuple[WeatherCapability, ...] = Field(default_factory=tuple)


def filter_inventory_candidates(
    candidates: list[OutfitInventoryCandidate],
    *,
    weather: WeatherRequirement | None,
) -> list[OutfitInventoryCandidate]:
    """Keep only available inventory that satisfies explicit weather constraints."""

    return [
        candidate
        for candidate in candidates
        if candidate.item.is_available
        and _meets_weather_requirement(candidate, weather)
    ]


def _meets_weather_requirement(
    candidate: OutfitInventoryCandidate,
    weather: WeatherRequirement | None,
) -> bool:
    if weather is None or weather.condition != "rain":
        return True
    return "rain_ready" in candidate.weather_capabilities
