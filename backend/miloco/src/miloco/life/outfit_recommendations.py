# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Deterministic, owner-bound Outfit recommendation contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from miloco.life.outfit_feedback_events import OutfitFeedbackEvent
from miloco.life.outfit_moments import OutfitMoment

OutfitRecommendationStatus = Literal[
    "needs_context",
    "ready",
    "insufficient_inventory",
]
OutfitDayKind = Literal["workday", "rest_day"]


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _require_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("value must not be blank")
    return value


class OutfitScenarioInput(BaseModel):
    """Structured context collected before deterministic outfit composition."""

    model_config = ConfigDict(extra="forbid")

    occasion: str | None = None
    activity: str | None = None
    day_kind: OutfitDayKind | None = None
    weather_summary: str | None = None

    _normalize_occasion = field_validator("occasion")(_normalize_optional_text)
    _normalize_activity = field_validator("activity")(_normalize_optional_text)
    _normalize_weather = field_validator("weather_summary")(_normalize_optional_text)

    def has_context(self) -> bool:
        """Require an explicit human scenario before using host context as a tie-breaker."""
        return bool(self.occasion or self.activity)


class OutfitRecommendationOption(BaseModel):
    """One inventory-only outfit option with stable selection identity."""

    model_config = ConfigDict(frozen=True)

    option_id: str
    item_ids: tuple[str, ...]
    composition_type: Literal["top_bottom_shoes", "dress_shoes"]

    _validate_option_id = field_validator("option_id")(_require_text)

    @model_validator(mode="after")
    def _validate_items(self) -> "OutfitRecommendationOption":
        if not self.item_ids or any(not item_id.strip() for item_id in self.item_ids):
            raise ValueError("recommendation item ids must not be blank")
        return self


class OutfitRecommendationSnapshot(BaseModel):
    """Private, immutable evidence for a recommendation the user can later select."""

    model_config = ConfigDict(frozen=True)

    recommendation_id: str
    owner_person_id: str
    scenario: OutfitScenarioInput
    options: tuple[OutfitRecommendationOption, ...]
    created_at_ms: int = Field(ge=0)

    _validate_recommendation_id = field_validator("recommendation_id")(_require_text)
    _validate_owner = field_validator("owner_person_id")(_require_text)

    @model_validator(mode="after")
    def _validate_options(self) -> "OutfitRecommendationSnapshot":
        if not self.options:
            raise ValueError("recommendation snapshots require at least one option")
        if len({option.option_id for option in self.options}) != len(self.options):
            raise ValueError("recommendation option ids must be unique")
        return self


class OutfitRecommendationResult(BaseModel):
    """Public result for either a context question or inventory-only options."""

    model_config = ConfigDict(frozen=True)

    status: OutfitRecommendationStatus
    recommendation_id: str | None = None
    options: tuple[OutfitRecommendationOption, ...] = ()
    missing_context: tuple[str, ...] = ()
    inventory_hints: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_state(self) -> "OutfitRecommendationResult":
        if self.status == "needs_context":
            if self.recommendation_id is not None or self.options:
                raise ValueError(
                    "context requests cannot contain recommendation options"
                )
            if not self.missing_context:
                raise ValueError("context requests must describe missing context")
        elif self.status == "ready":
            if self.recommendation_id is None or not self.options:
                raise ValueError("ready results require a snapshot and options")
        elif (self.recommendation_id is None) != (not self.options):
            raise ValueError(
                "inventory-limited results must contain both a snapshot and options"
            )
        return self


class ConfirmedOutfitWear(BaseModel):
    """Replay-safe output of an explicit wear confirmation and its moment."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    moment_id: str
    recommendation_id: str
    item_ids: tuple[str, ...]
    event: OutfitFeedbackEvent
    moment: OutfitMoment

    _validate_event_id = field_validator("event_id")(_require_text)
    _validate_moment_id = field_validator("moment_id")(_require_text)
    _validate_recommendation_id = field_validator("recommendation_id")(_require_text)

    @model_validator(mode="after")
    def _validate_items(self) -> "ConfirmedOutfitWear":
        if not self.item_ids or any(not item_id.strip() for item_id in self.item_ids):
            raise ValueError("confirmed wear item ids must not be blank")
        if self.event.event_id != self.event_id:
            raise ValueError("confirmed wear event must match its id")
        if self.moment.moment_id != self.moment_id:
            raise ValueError("confirmed wear moment must match its id")
        if self.event.recommendation_id != self.recommendation_id:
            raise ValueError("confirmed wear event must match recommendation")
        if self.moment.recommendation_id != self.recommendation_id:
            raise ValueError("confirmed wear moment must match recommendation")
        if (
            self.event.item_ids != self.item_ids
            or self.moment.item_ids != self.item_ids
        ):
            raise ValueError("confirmed wear item ids must match event and moment")
        return self
