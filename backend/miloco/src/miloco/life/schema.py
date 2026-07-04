# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Life domain schemas for outfit and cooking demo flows."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

WardrobeCategory = Literal[
    "top",
    "bottom",
    "dress",
    "outerwear",
    "shoes",
    "bag",
    "accessory",
]
WardrobeStatus = Literal["active", "laundry", "retired", "unknown"]
LifeSourceType = Literal["photo", "product_link", "manual", "camera", "mimo_mock"]

PantryCategory = Literal[
    "vegetable",
    "protein",
    "staple",
    "seasoning",
    "drink",
    "frozen",
    "snack",
    "other",
]
PantryStorage = Literal["fridge", "freezer", "room_temp", "unknown"]
Freshness = Literal["fresh", "normal", "use_soon", "unknown"]

LifeDomain = Literal["outfit", "cooking"]

_ABSOLUTE_SAFETY_CLAIMS = (
    "already cooked",
    "fully cooked",
    "must turn off",
    "safety is confirmed",
    "confirmed safe",
    "已经熟了",
    "完全熟了",
    "必须关火",
    "确认安全",
    "已经安全",
)


def _strip_nonempty(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("value must not be blank")
    return v


def _normalize_optional_str(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


def _normalize_tag_list(values: list[str]) -> list[str]:
    return [tag for raw in values if (tag := raw.strip())]


def _normalize_ref_list(values: list[str]) -> list[str]:
    return [_strip_nonempty(value) for value in values]


def _reject_absolute_safety_claim_text(text: str) -> None:
    text = text.lower()
    for claim in _ABSOLUTE_SAFETY_CLAIMS:
        if claim in text:
            raise ValueError(
                "kitchen safety notes must use conservative wording and require user confirmation"
            )


class WardrobeItem(BaseModel):
    id: str
    owner_person_id: str | None = None
    name: str
    category: WardrobeCategory
    colors: list[str] = Field(default_factory=list)
    material_tags: list[str] = Field(default_factory=list)
    season_tags: list[str] = Field(default_factory=list)
    formality: int = Field(ge=1, le=5)
    warmth_level: int = Field(ge=1, le=5)
    style_tags: list[str] = Field(default_factory=list)
    source_type: LifeSourceType
    source_ref: str | None = None
    image_refs: list[str] = Field(default_factory=list)
    status: WardrobeStatus = "unknown"
    confidence: float = Field(ge=0, le=1)
    notes: str | None = None

    _strip_id = field_validator("id")(_strip_nonempty)
    _strip_name = field_validator("name")(_strip_nonempty)
    _norm_owner_person_id = field_validator("owner_person_id")(_normalize_optional_str)
    _norm_notes = field_validator("notes")(_normalize_optional_str)
    _norm_source_ref = field_validator("source_ref")(_normalize_optional_str)
    _norm_colors = field_validator("colors")(_normalize_tag_list)
    _norm_materials = field_validator("material_tags")(_normalize_tag_list)
    _norm_seasons = field_validator("season_tags")(_normalize_tag_list)
    _norm_styles = field_validator("style_tags")(_normalize_tag_list)


class PantryItem(BaseModel):
    id: str
    name: str
    category: PantryCategory
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = None
    storage: PantryStorage
    expires_at: str | None = None
    freshness: Freshness = "unknown"
    diet_tags: list[str] = Field(default_factory=list)
    source_type: LifeSourceType
    source_ref: str | None = None
    confidence: float = Field(ge=0, le=1)
    notes: str | None = None

    _strip_id = field_validator("id")(_strip_nonempty)
    _strip_name = field_validator("name")(_strip_nonempty)
    _norm_unit = field_validator("unit")(_normalize_optional_str)
    _norm_source_ref = field_validator("source_ref")(_normalize_optional_str)
    _norm_notes = field_validator("notes")(_normalize_optional_str)
    _norm_diet_tags = field_validator("diet_tags")(_normalize_tag_list)


class LifePreference(BaseModel):
    person_id: str | None = None
    domain: LifeDomain
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None

    _norm_notes = field_validator("notes")(_normalize_optional_str)
    _norm_person_id = field_validator("person_id")(_normalize_optional_str)
    _norm_tags = field_validator("tags")(_normalize_tag_list)


class OutfitRecommendationRequest(BaseModel):
    wardrobe_item_ids: list[str] = Field(default_factory=list)
    person_id: str | None = None
    occasion: str
    weather: str | None = None
    preference_tags: list[str] = Field(default_factory=list)

    _strip_occasion = field_validator("occasion")(_strip_nonempty)
    _norm_person_id = field_validator("person_id")(_normalize_optional_str)
    _norm_weather = field_validator("weather")(_normalize_optional_str)
    _norm_preference_tags = field_validator("preference_tags")(_normalize_tag_list)
    _norm_wardrobe_item_ids = field_validator("wardrobe_item_ids")(_normalize_ref_list)


class CookingRecommendationRequest(BaseModel):
    pantry_item_ids: list[str] = Field(min_length=1)
    people_count: int = Field(ge=1)
    time_budget_minutes: int = Field(ge=1)
    taste_tags: list[str] = Field(default_factory=list)
    avoid_tags: list[str] = Field(default_factory=list)

    _norm_taste_tags = field_validator("taste_tags")(_normalize_tag_list)
    _norm_avoid_tags = field_validator("avoid_tags")(_normalize_tag_list)
    _norm_pantry_item_ids = field_validator("pantry_item_ids")(_normalize_ref_list)


class RecommendationOption(BaseModel):
    title: str
    summary: str
    rationale: list[str] = Field(default_factory=list)
    item_ids: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)

    _strip_title = field_validator("title")(_strip_nonempty)
    _strip_summary = field_validator("summary")(_strip_nonempty)
    _norm_rationale = field_validator("rationale")(_normalize_tag_list)
    _norm_safety_notes = field_validator("safety_notes")(_normalize_tag_list)
    _norm_item_ids = field_validator("item_ids")(_normalize_ref_list)

    @model_validator(mode="after")
    def _reject_absolute_safety_claims(self) -> "RecommendationOption":
        _reject_absolute_safety_claim_text(
            " ".join([self.title, self.summary, *self.safety_notes])
        )
        return self


class RecommendationResult(BaseModel):
    domain: LifeDomain
    options: list[RecommendationOption] = Field(min_length=1)
    broadcast_text: str | None = None

    _norm_broadcast_text = field_validator("broadcast_text")(_normalize_optional_str)

    @model_validator(mode="after")
    def _reject_absolute_broadcast_safety_claims(self) -> "RecommendationResult":
        if self.broadcast_text is not None:
            _reject_absolute_safety_claim_text(self.broadcast_text)
        return self
