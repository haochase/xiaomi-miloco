# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Privacy-bounded request and response DTOs for the Outfit wardrobe API."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from miloco.outfit.wardrobe import (
    ConfirmedWardrobeItem,
    WardrobeAvailability,
    WardrobeCategory,
    WardrobeItemDraft,
    WardrobeSourceEvidence,
    WardrobeSourceType,
)

WardrobeApiProblemCode: TypeAlias = Literal[
    "wardrobe_draft_not_found",
    "wardrobe_draft_confirmation_required",
    "wardrobe_duplicate_external_source",
]


class WardrobeApiProblem(BaseModel):
    """One fixed public failure code without storage or owner details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: WardrobeApiProblemCode


class CreateWardrobeDraftRequest(BaseModel):
    """Accept user-supplied item facts without an owner selector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    category: WardrobeCategory
    source_evidence: tuple[WardrobeSourceEvidence, ...] = Field(min_length=1)


class ConfirmWardrobeDraftRequest(BaseModel):
    """Require an explicit confirmation before inventory promotion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    confirmed_by_user: Literal[True]


class WardrobeDraftResponse(BaseModel):
    """Expose a pending item without owner or source-reference leakage."""

    model_config = ConfigDict(frozen=True)

    draft_id: str
    name: str
    category: WardrobeCategory
    source_types: tuple[WardrobeSourceType, ...]
    status: Literal["pending"]

    @classmethod
    def from_domain(cls, draft: WardrobeItemDraft) -> WardrobeDraftResponse:
        """Map one internal draft to its safe panel representation."""

        return cls(
            draft_id=draft.draft_id,
            name=draft.name,
            category=draft.category,
            source_types=tuple(
                evidence.source_type for evidence in draft.source_evidence
            ),
            status=draft.status,
        )


class ConfirmedWardrobeItemResponse(BaseModel):
    """Expose an inventory item without owner or source-reference leakage."""

    model_config = ConfigDict(frozen=True)

    item_id: str
    name: str
    category: WardrobeCategory
    source_types: tuple[WardrobeSourceType, ...]
    status: Literal["confirmed"]
    availability: WardrobeAvailability

    @classmethod
    def from_domain(
        cls,
        item: ConfirmedWardrobeItem,
    ) -> ConfirmedWardrobeItemResponse:
        """Map one internal confirmed item to its safe panel representation."""

        return cls(
            item_id=item.item_id,
            name=item.name,
            category=item.category,
            source_types=tuple(
                evidence.source_type for evidence in item.source_evidence
            ),
            status=item.status,
            availability=item.availability,
        )
