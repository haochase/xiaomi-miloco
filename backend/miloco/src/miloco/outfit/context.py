# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Structured scenario facts and minimal clarification for Outfit requests."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, field_validator

DayKind: TypeAlias = Literal["workday", "rest_day", "unknown"]
ClarificationField: TypeAlias = Literal["occasion_or_activity"]


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class OutfitRecommendationContext(BaseModel):
    """Scenario facts only; the host injects the owner outside this request model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    occasion: str | None = None
    activity: str | None = None
    day_kind: DayKind = "unknown"

    _normalize_occasion = field_validator("occasion")(_normalize_optional_text)
    _normalize_activity = field_validator("activity")(_normalize_optional_text)


class OutfitClarification(BaseModel):
    """The sole minimum question needed before a recommendation can continue."""

    model_config = ConfigDict(frozen=True)

    field: ClarificationField
    prompt: str


def next_clarification(
    context: OutfitRecommendationContext,
) -> OutfitClarification | None:
    """Ask once only when both occasion and activity are absent."""

    if context.occasion is not None or context.activity is not None:
        return None
    return OutfitClarification(
        field="occasion_or_activity",
        prompt="What occasion or activity should this outfit support?",
    )
