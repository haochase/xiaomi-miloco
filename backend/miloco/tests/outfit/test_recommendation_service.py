# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Golden contracts for the primary-user deterministic recommendation pipeline."""

from pathlib import Path

import pytest
from miloco.outfit.context import OutfitClarification, OutfitRecommendationContext
from miloco.outfit.filtering import WeatherRequirement
from miloco.outfit.recommendation import OutfitRecommendationResult
from miloco.outfit.recommendation_service import (
    OutfitRecommendationResponse,
    OutfitRecommendationService,
)
from miloco.outfit.storage import OutfitStorage
from miloco.outfit.wardrobe import WardrobeSourceEvidence
from miloco.outfit.wardrobe_repo import WardrobeRepository
from miloco.outfit.wardrobe_service import WardrobeService


class _WeatherPort:
    def __init__(self, weather: WeatherRequirement | None) -> None:
        self._weather = weather

    def current_requirement(self) -> WeatherRequirement | None:
        return self._weather


class _CapabilityPort:
    def __init__(self, rain_ready_item_ids: set[str]) -> None:
        self._rain_ready_item_ids = rain_ready_item_ids

    def weather_capabilities_for(self, item_id: str) -> tuple[str, ...]:
        return ("rain_ready",) if item_id in self._rain_ready_item_ids else ()


def _wardrobe_service(tmp_path: Path) -> WardrobeService:
    sequence = iter(range(1, 20))
    return WardrobeService(
        WardrobeRepository(OutfitStorage(tmp_path / "outfit.db")),
        primary_person_id="primary-user",
        clock_ms=lambda: next(sequence),
        draft_id_factory=lambda: f"draft-{next(sequence)}",
    )


def _confirm_item(service: WardrobeService, *, name: str, category: str) -> str:
    draft = service.create_draft(
        name=name,
        category=category,
        source_evidence=(
            WardrobeSourceEvidence(source_type="manual", reference=f"closet {name}"),
        ),
    )
    return service.confirm_draft(draft.draft_id, confirmed_by_user=True).item_id


def test_missing_scene_returns_one_clarification_without_reading_inventory(
    tmp_path: Path,
):
    service = OutfitRecommendationService(
        _wardrobe_service(tmp_path),
        weather_port=_WeatherPort(None),
        capability_port=_CapabilityPort(set()),
    )

    response = service.recommend(OutfitRecommendationContext())

    assert response.status == "needs_context"
    assert response.clarification is not None
    assert response.result is None


@pytest.mark.parametrize(
    "values",
    [
        {"status": "needs_context"},
        {
            "status": "needs_context",
            "clarification": OutfitClarification(
                field="occasion_or_activity",
                prompt="What occasion or activity should this outfit support?",
            ),
            "result": OutfitRecommendationResult(
                status="insufficient_inventory",
                options=(),
                message="No complete options.",
            ),
        },
        {"status": "ready"},
        {
            "status": "ready",
            "result": OutfitRecommendationResult(
                status="insufficient_inventory",
                options=(),
                message="No complete options.",
            ),
        },
        {"status": "insufficient_inventory"},
        {
            "status": "insufficient_inventory",
            "result": OutfitRecommendationResult(
                status="ready",
                options=(),
                message="Ready.",
            ),
        },
    ],
)
def test_response_rejects_status_payload_mismatches(values: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        OutfitRecommendationResponse.model_validate(values)


def test_recommendation_exposes_wardrobe_owner_read_only(tmp_path: Path) -> None:
    wardrobe = _wardrobe_service(tmp_path)
    service = OutfitRecommendationService(
        wardrobe,
        weather_port=_WeatherPort(None),
        capability_port=_CapabilityPort(set()),
    )

    assert wardrobe.primary_person_id == "primary-user"
    assert service.primary_person_id == "primary-user"


def test_rainy_context_returns_only_confirmed_rain_ready_inventory_options(
    tmp_path: Path,
):
    wardrobe = _wardrobe_service(tmp_path)
    rain_ready_ids = {
        (rain_top := _confirm_item(wardrobe, name="rain top", category="top")),
        (rain_bottom := _confirm_item(wardrobe, name="rain bottom", category="bottom")),
        (rain_shoes := _confirm_item(wardrobe, name="rain shoes", category="shoes")),
        (rain_dress := _confirm_item(wardrobe, name="rain dress", category="dress")),
    }
    dry_only_top = _confirm_item(wardrobe, name="dry-only top", category="top")
    service = OutfitRecommendationService(
        wardrobe,
        weather_port=_WeatherPort(WeatherRequirement(condition="rain")),
        capability_port=_CapabilityPort(rain_ready_ids),
    )

    response = service.recommend(
        OutfitRecommendationContext(occasion="rainy client meeting")
    )

    assert response.status == "ready"
    assert response.result is not None
    assert [option.candidate.item_ids for option in response.result.options] == [
        (rain_top, rain_bottom, rain_shoes),
        (rain_dress, rain_shoes),
    ]
    assert all(
        item_id != dry_only_top
        for option in response.result.options
        for item_id in option.candidate.item_ids
    )


def test_one_complete_inventory_outfit_remains_insufficient_without_padding(
    tmp_path: Path,
):
    wardrobe = _wardrobe_service(tmp_path)
    item_ids = {
        _confirm_item(wardrobe, name="navy top", category="top"),
        _confirm_item(wardrobe, name="gray bottom", category="bottom"),
        _confirm_item(wardrobe, name="white shoes", category="shoes"),
    }
    service = OutfitRecommendationService(
        wardrobe,
        weather_port=_WeatherPort(None),
        capability_port=_CapabilityPort(item_ids),
    )

    response = service.recommend(OutfitRecommendationContext(activity="commute"))

    assert response.status == "insufficient_inventory"
    assert response.result is not None
    assert len(response.result.options) == 1
