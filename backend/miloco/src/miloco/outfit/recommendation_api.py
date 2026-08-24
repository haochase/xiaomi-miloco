# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Strict request and opaque snapshot DTOs for Outfit recommendations."""

from __future__ import annotations

import re
from typing import Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from miloco.outfit.context import DayKind, OutfitRecommendationContext
from miloco.outfit.recommendation import (
    OutfitRecommendationResult,
    RecommendationStatus,
)

RecommendationApiProblemCode: TypeAlias = Literal[
    "recommendation_needs_context",
    "recommendation_insufficient_inventory",
]
_OPAQUE_SNAPSHOT_ID = re.compile(r"^rec-[a-z0-9][a-z0-9-]{0,63}$")


def _require_nonempty_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("must not be blank")
    return normalized


class RecommendationApiProblem(BaseModel):
    """One fixed public failure code without inventory or model details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: RecommendationApiProblemCode


class CreateRecommendationRequest(BaseModel):
    """Accept scenario facts only; host composition supplies the inventory owner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    occasion: str | None = None
    activity: str | None = None
    day_kind: DayKind = "unknown"

    def to_context(self) -> OutfitRecommendationContext:
        """Map the public request to the existing owner-free domain context."""

        return OutfitRecommendationContext(
            occasion=self.occasion,
            activity=self.activity,
            day_kind=self.day_kind,
        )


class RecommendationSnapshot(BaseModel):
    """Immutable, media-free candidate fact shared by later Outfit flows."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: str
    context: OutfitRecommendationContext
    status: RecommendationStatus
    option_item_ids: tuple[tuple[str, ...], ...] = Field(max_length=3)
    ranking_version: str
    created_at_ms: int = Field(ge=0)

    _normalize_ranking_version = field_validator("ranking_version")(
        _require_nonempty_text
    )

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, snapshot_id: str) -> str:
        """Accept only a service-generated opaque identifier shape."""

        if not _OPAQUE_SNAPSHOT_ID.fullmatch(snapshot_id):
            raise ValueError("snapshot_id must be opaque")
        return snapshot_id

    @field_validator("option_item_ids")
    @classmethod
    def validate_option_item_ids(
        cls,
        options: tuple[tuple[str, ...], ...],
    ) -> tuple[tuple[str, ...], ...]:
        """Reject blank candidate IDs before they become a cross-flow reference."""

        for option in options:
            if len(option) < 2:
                raise ValueError("candidate options must contain at least two item IDs")
            for item_id in option:
                _require_nonempty_text(item_id)
        return options

    @model_validator(mode="after")
    def validate_status_option_count(self) -> Self:
        """Keep externally visible state aligned with the deterministic result contract."""

        option_count = len(self.option_item_ids)
        if self.status == "ready" and not 2 <= option_count <= 3:
            raise ValueError("ready snapshots require two or three candidate options")
        if self.status == "insufficient_inventory" and option_count > 1:
            raise ValueError(
                "insufficient inventory snapshots allow at most one candidate option"
            )
        return self


def snapshot_from_result(
    *,
    snapshot_id: str,
    context: OutfitRecommendationContext,
    result: OutfitRecommendationResult,
    created_at_ms: int,
    ranking_version: str,
) -> RecommendationSnapshot:
    """Persist only bounded candidate item IDs, never ranking prose or raw media."""

    return RecommendationSnapshot(
        snapshot_id=snapshot_id,
        context=context,
        status=result.status,
        option_item_ids=tuple(option.candidate.item_ids for option in result.options),
        ranking_version=ranking_version,
        created_at_ms=created_at_ms,
    )
