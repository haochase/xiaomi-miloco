# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Immutable projections and reviewable labels for Outfit history moments."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OutfitMomentTagType = Literal[
    "decision_longer_than_usual",
    "rare_color_return",
    "dressed_up_after_gap",
    "style_outlier_confirmed",
    "repeat_favorite",
    "user_defined",
]
OutfitMomentTagSource = Literal["rule", "model", "user"]
OutfitMomentTagReviewStatus = Literal["pending", "confirmed", "edited", "rejected"]
OutfitMomentSignalType = Literal["repeat_favorite", "rare_color_return"]

_SYSTEM_TAG_FORBIDDEN_TERMS = (
    "anxiety",
    "depression",
    "personality",
    "weight",
    "body shape",
    "焦虑",
    "抑郁",
    "人格",
    "身材",
    "体重",
    "社恐",
    "i人",
)


class OutfitMoment(BaseModel):
    """A rebuildable, owner-scoped projection of an explicit wear confirmation."""

    model_config = ConfigDict(frozen=True)

    moment_id: str
    owner_person_id: str
    occurred_at_ms: int = Field(ge=0)
    timezone: str
    recommendation_id: str
    confirmed_wear_event_id: str
    item_ids: tuple[str, ...]
    color_labels: tuple[str, ...] = ()
    source_event_ids: tuple[str, ...]
    user_note: str | None = None
    created_at_ms: int = Field(ge=0)
    projection_version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _validate_refs(self) -> "OutfitMoment":
        if not self.moment_id.strip():
            raise ValueError("moment id must not be blank")
        if not self.owner_person_id.strip():
            raise ValueError("owner person id must not be blank")
        if not self.timezone.strip():
            raise ValueError("timezone must not be blank")
        if not self.recommendation_id.strip():
            raise ValueError("recommendation id must not be blank")
        if not self.confirmed_wear_event_id.strip():
            raise ValueError("confirmed wear event id must not be blank")
        if self.confirmed_wear_event_id not in self.source_event_ids:
            raise ValueError("source events must contain confirmed wear event")
        if not self.item_ids:
            raise ValueError("moment must contain confirmed worn items")
        if any(not item_id.strip() for item_id in self.item_ids):
            raise ValueError("item ids must not be blank")
        if any(not color.strip() or len(color) > 40 for color in self.color_labels):
            raise ValueError("color labels must be non-blank and at most 40 characters")
        if any(not event_id.strip() for event_id in self.source_event_ids):
            raise ValueError("source event ids must not be blank")
        return self


class OutfitMomentTag(BaseModel):
    """A user-reviewable label with explicit structured evidence."""

    model_config = ConfigDict(frozen=True)

    tag_id: str
    moment_id: str
    tag_type: OutfitMomentTagType
    label: str
    narrative: str
    evidence_signal_ids: tuple[str, ...]
    source: OutfitMomentTagSource
    confidence: float = Field(ge=0, le=1)
    review_status: OutfitMomentTagReviewStatus
    dedupe_key: str
    generator_version: str

    @model_validator(mode="after")
    def _validate_evidence(self) -> "OutfitMomentTag":
        if not self.tag_id.strip() or not self.moment_id.strip():
            raise ValueError("tag and moment ids must not be blank")
        if not self.label.strip() or not self.narrative.strip():
            raise ValueError("tag label and narrative must not be blank")
        if not self.dedupe_key.strip() or not self.generator_version.strip():
            raise ValueError("tag dedupe key and generator version must not be blank")
        if self.source in {"rule", "model"} and not self.evidence_signal_ids:
            raise ValueError("system tags require at least one evidence signal")
        if any(not signal_id.strip() for signal_id in self.evidence_signal_ids):
            raise ValueError("evidence signal ids must not be blank")
        if self.source == "user" and self.tag_type != "user_defined":
            raise ValueError("user tags must use the user_defined tag type")
        if self.source != "user":
            copy = f"{self.label}\n{self.narrative}".lower()
            if any(term in copy for term in _SYSTEM_TAG_FORBIDDEN_TERMS):
                raise ValueError(
                    "system tags must not include sensitive inference terms"
                )
        return self


class OutfitMomentSignal(BaseModel):
    """A deterministic, versioned evidence signal used to propose a tag."""

    model_config = ConfigDict(frozen=True)

    signal_id: str
    moment_id: str
    signal_type: OutfitMomentSignalType
    value_json: dict[str, int | str]
    evidence_event_ids: tuple[str, ...]
    rule_version: str

    @model_validator(mode="after")
    def _validate_signal(self) -> "OutfitMomentSignal":
        if not self.signal_id.strip() or not self.moment_id.strip():
            raise ValueError("signal and moment ids must not be blank")
        if not self.evidence_event_ids or any(
            not event_id.strip() for event_id in self.evidence_event_ids
        ):
            raise ValueError("signals require non-blank evidence event ids")
        if not self.rule_version.strip():
            raise ValueError("signal rule version must not be blank")
        return self
