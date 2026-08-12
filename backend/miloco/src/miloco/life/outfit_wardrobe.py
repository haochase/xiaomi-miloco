# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Primary-user wardrobe facts with an explicit draft-to-confirm lifecycle."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

WardrobeCategory = Literal[
    "top",
    "bottom",
    "dress",
    "outerwear",
    "shoes",
    "bag",
    "accessory",
]
WardrobeSourceType = Literal["manual", "photo", "product_link"]
WardrobeDraftStatus = Literal["pending", "confirmed", "discarded"]


def _require_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("value must not be blank")
    return value


class WardrobeDraftInput(BaseModel):
    """User-provided item facts awaiting explicit confirmation."""

    name: str
    category: WardrobeCategory
    source_type: WardrobeSourceType
    source_reference: str

    _validate_name = field_validator("name")(_require_text)
    _validate_source_reference = field_validator("source_reference")(_require_text)


class WardrobeItemDraft(BaseModel):
    """A private draft whose lifecycle is controlled by explicit user actions."""

    model_config = ConfigDict(frozen=True)

    draft_id: str
    owner_person_id: str
    name: str
    category: WardrobeCategory
    source_type: WardrobeSourceType
    source_reference: str
    created_at_ms: int
    status: WardrobeDraftStatus = "pending"

    _validate_draft_id = field_validator("draft_id")(_require_text)
    _validate_owner = field_validator("owner_person_id")(_require_text)
    _validate_name = field_validator("name")(_require_text)
    _validate_source_reference = field_validator("source_reference")(_require_text)


class ConfirmedWardrobeItem(BaseModel):
    """An inventory item made usable only by an explicit user confirmation."""

    model_config = ConfigDict(frozen=True)

    item_id: str
    owner_person_id: str
    name: str
    category: WardrobeCategory
    source_type: WardrobeSourceType
    source_reference: str
    confirmed_at_ms: int

    _validate_item_id = field_validator("item_id")(_require_text)
    _validate_owner = field_validator("owner_person_id")(_require_text)
    _validate_name = field_validator("name")(_require_text)
    _validate_source_reference = field_validator("source_reference")(_require_text)
