# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Primary-user application service for the deterministic Outfit recommendation chain."""

from __future__ import annotations

from typing import Literal, Protocol, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, model_validator

from miloco.outfit.composition import compose_outfit_candidates
from miloco.outfit.context import (
    OutfitClarification,
    OutfitRecommendationContext,
    next_clarification,
)
from miloco.outfit.filtering import (
    OutfitInventoryCandidate,
    WeatherCapability,
    WeatherRequirement,
    filter_inventory_candidates,
)
from miloco.outfit.ranking import rank_outfit_candidates
from miloco.outfit.recommendation import (
    OutfitRecommendationResult,
    build_recommendation_result,
)
from miloco.outfit.wardrobe import ConfirmedWardrobeItem
from miloco.outfit.wardrobe_service import WardrobeService

RecommendationResponseStatus: TypeAlias = Literal[
    "needs_context",
    "ready",
    "insufficient_inventory",
]


class WeatherRequirementPort(Protocol):
    """Host-owned resolved weather fact for the currently configured primary user."""

    def current_requirement(self) -> WeatherRequirement | None: ...


class WardrobeCapabilityPort(Protocol):
    """Optional item capabilities without giving the service a broad metadata store."""

    def weather_capabilities_for(
        self,
        item_id: str,
    ) -> tuple[WeatherCapability, ...]: ...


class OutfitRecommendationResponse(BaseModel):
    """One safe result: either a single clarification or a real inventory result."""

    model_config = ConfigDict(frozen=True)

    status: RecommendationResponseStatus
    clarification: OutfitClarification | None = None
    result: OutfitRecommendationResult | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> Self:
        if self.status == "needs_context":
            if self.clarification is None or self.result is not None:
                raise ValueError(
                    "needs_context requires one clarification and no result"
                )
            return self

        if self.clarification is not None or self.result is None:
            raise ValueError(
                "recommendation result statuses require a result and no clarification"
            )
        if self.result.status != self.status:
            raise ValueError("response status must match result status")
        return self


class OutfitRecommendationService:
    """Join host-injected ports to the primary-user's deterministic Outfit chain."""

    def __init__(
        self,
        wardrobe_service: WardrobeService,
        *,
        weather_port: WeatherRequirementPort,
        capability_port: WardrobeCapabilityPort,
    ) -> None:
        self._wardrobe_service = wardrobe_service
        self._weather_port = weather_port
        self._capability_port = capability_port

    @property
    def primary_person_id(self) -> str:
        """Return the owner whose confirmed inventory backs recommendations."""

        return self._wardrobe_service.primary_person_id

    def recommend(
        self,
        context: OutfitRecommendationContext,
    ) -> OutfitRecommendationResponse:
        """Return one clarification or a bounded result sourced only from confirmed inventory."""

        clarification = next_clarification(context)
        if clarification is not None:
            return OutfitRecommendationResponse(
                status="needs_context",
                clarification=clarification,
            )

        candidates = _inventory_candidates(
            self._wardrobe_service.list_confirmed_available_items(),
            self._capability_port,
        )
        filtered_candidates = filter_inventory_candidates(
            candidates,
            weather=self._weather_port.current_requirement(),
        )
        result = build_recommendation_result(
            rank_outfit_candidates(compose_outfit_candidates(filtered_candidates))
        )
        return OutfitRecommendationResponse(status=result.status, result=result)


def _inventory_candidates(
    items: tuple[ConfirmedWardrobeItem, ...],
    capability_port: WardrobeCapabilityPort,
) -> list[OutfitInventoryCandidate]:
    return [
        OutfitInventoryCandidate(
            item=item,
            weather_capabilities=capability_port.weather_capabilities_for(item.item_id),
        )
        for item in items
    ]
