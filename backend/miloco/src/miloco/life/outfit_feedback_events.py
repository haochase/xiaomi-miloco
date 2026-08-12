# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Immutable user-feedback facts consumed by Outfit projections."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OutfitFeedbackEventType = Literal[
    "recommendation_presented",
    "recommendation_selected",
    "recommendation_rejected",
    "try_on_evaluated",
    "try_on_correction_requested",
    "wear_confirmed",
]


class OutfitFeedbackEvent(BaseModel):
    """An append-only user fact, never a learned preference or generated label."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    owner_person_id: str
    event_type: OutfitFeedbackEventType
    recommendation_id: str
    item_ids: tuple[str, ...]
    occurred_at_ms: int = Field(ge=0)
    confirmed_by_user: bool = False
    evidence_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_fact(self) -> "OutfitFeedbackEvent":
        if not self.event_id.strip() or not self.owner_person_id.strip():
            raise ValueError("event and owner ids must not be blank")
        if not self.recommendation_id.strip():
            raise ValueError("recommendation id must not be blank")
        if not self.item_ids or any(not item_id.strip() for item_id in self.item_ids):
            raise ValueError("event item ids must not be blank")
        if self.event_type == "wear_confirmed" and not self.confirmed_by_user:
            raise ValueError("wear events require explicit user confirmation")
        return self
