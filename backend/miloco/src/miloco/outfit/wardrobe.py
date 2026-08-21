# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Pure wardrobe facts for the single-primary-user Outfit plugin."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator

WardrobeCategory: TypeAlias = Literal[
    "top",
    "bottom",
    "dress",
    "outerwear",
    "shoes",
    "bag",
    "accessory",
]
WardrobeSourceType: TypeAlias = Literal["manual", "photo", "product_link"]
WardrobeAvailability: TypeAlias = Literal["available", "laundry", "retired"]

EXACT_SOURCE_DEDUPLICATED_TYPES = frozenset({"photo", "product_link"})


def _require_nonempty_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("must not be blank")
    return normalized


class WardrobeSourceEvidence(BaseModel):
    """A user-supplied source reference for one wardrobe item draft."""

    model_config = ConfigDict(frozen=True)

    source_type: WardrobeSourceType
    reference: str

    _normalize_reference = field_validator("reference")(_require_nonempty_text)


class WardrobeItemDraft(BaseModel):
    """An item that cannot enter recommendation inventory until confirmed."""

    model_config = ConfigDict(frozen=True)

    draft_id: str
    owner_person_id: str
    name: str
    category: WardrobeCategory
    source_evidence: tuple[WardrobeSourceEvidence, ...] = Field(min_length=1)
    created_at_ms: int = Field(ge=0)
    status: Literal["pending"] = "pending"

    _normalize_draft_id = field_validator("draft_id")(_require_nonempty_text)
    _normalize_owner_person_id = field_validator("owner_person_id")(
        _require_nonempty_text
    )
    _normalize_name = field_validator("name")(_require_nonempty_text)


class ConfirmedWardrobeItem(BaseModel):
    """An explicitly confirmed item that can be filtered by availability."""

    model_config = ConfigDict(frozen=True)

    item_id: str
    owner_person_id: str
    name: str
    category: WardrobeCategory
    source_evidence: tuple[WardrobeSourceEvidence, ...] = Field(min_length=1)
    confirmed_at_ms: int = Field(ge=0)
    confirmed_by_user: Literal[True]
    status: Literal["confirmed"] = "confirmed"
    availability: WardrobeAvailability = "available"

    _normalize_item_id = field_validator("item_id")(_require_nonempty_text)
    _normalize_owner_person_id = field_validator("owner_person_id")(
        _require_nonempty_text
    )
    _normalize_name = field_validator("name")(_require_nonempty_text)

    @property
    def is_available(self) -> bool:
        """Return whether recommendation may use this confirmed item."""

        return self.availability == "available"


def requires_exact_source_deduplication(source_type: WardrobeSourceType) -> bool:
    """Return whether a source type has a stable external identity."""

    return source_type in EXACT_SOURCE_DEDUPLICATED_TYPES


def has_exact_external_source_duplicate(
    first: Iterable[WardrobeSourceEvidence],
    second: Iterable[WardrobeSourceEvidence],
) -> bool:
    """Compare only stable external source type/reference pairs.

    Manual notes are intentionally excluded because equal free text is not proof
    that two drafts represent the same physical item.
    """

    first_keys = _exact_external_source_keys(first)
    second_keys = _exact_external_source_keys(second)
    return bool(first_keys & second_keys)


def confirm_wardrobe_draft(
    draft: WardrobeItemDraft,
    *,
    item_id: str,
    confirmed_at_ms: int,
    confirmed_by_user: bool,
) -> ConfirmedWardrobeItem:
    """Promote a pending draft only after an explicit user decision."""

    if confirmed_by_user is not True:
        raise ValueError("explicit user confirmation is required")
    if confirmed_at_ms < draft.created_at_ms:
        raise ValueError("confirmation cannot predate draft creation")

    return ConfirmedWardrobeItem(
        item_id=item_id,
        owner_person_id=draft.owner_person_id,
        name=draft.name,
        category=draft.category,
        source_evidence=draft.source_evidence,
        confirmed_at_ms=confirmed_at_ms,
        confirmed_by_user=True,
    )


def _exact_external_source_keys(
    source_evidence: Iterable[WardrobeSourceEvidence],
) -> frozenset[tuple[WardrobeSourceType, str]]:
    return frozenset(
        (evidence.source_type, evidence.reference)
        for evidence in source_evidence
        if requires_exact_source_deduplication(evidence.source_type)
    )
