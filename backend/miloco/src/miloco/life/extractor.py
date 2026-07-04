# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Mock MiMo extraction helpers for the life domain demo."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from miloco.life.schema import LifePreference, PantryItem, WardrobeItem


class LifeExtractionResult(BaseModel):
    source_id: str = "mimo_mock"
    caption: str | None = None
    wardrobe_items: list[WardrobeItem] = Field(default_factory=list)
    pantry_items: list[PantryItem] = Field(default_factory=list)
    preferences: list[LifePreference] = Field(default_factory=list)
    low_confidence_notes: list[str] = Field(default_factory=list)

    @field_validator("low_confidence_notes")
    @classmethod
    def _drop_blank_notes(cls, values: list[str]) -> list[str]:
        return [note for raw in values if (note := raw.strip())]


def extract_life_assets_from_mimo_mock(
    payload: dict[str, Any] | str,
) -> LifeExtractionResult:
    """Convert a mock MiMo payload into validated life-domain assets.

    This intentionally stays deterministic for hackathon dry runs. Real MiMo
    API calls can swap in behind the same output shape later.
    """
    if isinstance(payload, str):
        return _extract_from_demo_text(payload)
    return _extract_from_structured_payload(payload)


def _extract_from_structured_payload(payload: dict[str, Any]) -> LifeExtractionResult:
    source_id = _clean_source_id(payload.get("source_id"))
    return LifeExtractionResult(
        source_id=source_id,
        caption=_optional_text(payload.get("caption")),
        wardrobe_items=[
            WardrobeItem(**_with_mock_source(raw, source_id))
            for raw in payload.get("wardrobe", [])
        ],
        pantry_items=[
            PantryItem(**_with_mock_source(raw, source_id))
            for raw in payload.get("pantry", [])
        ],
        preferences=[LifePreference(**raw) for raw in payload.get("preferences", [])],
        low_confidence_notes=payload.get("low_confidence_notes", []),
    )


def _extract_from_demo_text(text: str) -> LifeExtractionResult:
    normalized = text.lower()
    wardrobe_items = []
    pantry_items = []

    if "dark gray blazer" in normalized:
        wardrobe_items.append(
            WardrobeItem(
                id="text_blazer_gray",
                name="dark gray blazer",
                category="outerwear",
                colors=["gray"],
                material_tags=[],
                season_tags=["spring", "autumn"],
                formality=4,
                warmth_level=3,
                style_tags=["formal", "minimal"],
                source_type="mimo_mock",
                source_ref="demo_text",
                confidence=0.58,
                notes="Extracted by mock text heuristic; please confirm before saving.",
            )
        )
    if "white shirt" in normalized:
        wardrobe_items.append(
            WardrobeItem(
                id="text_shirt_white",
                name="white shirt",
                category="top",
                colors=["white"],
                material_tags=["cotton"],
                season_tags=["spring", "summer", "autumn"],
                formality=4,
                warmth_level=2,
                style_tags=["formal", "simple"],
                source_type="mimo_mock",
                source_ref="demo_text",
                confidence=0.58,
                notes="Extracted by mock text heuristic; please confirm before saving.",
            )
        )

    pantry_patterns = [
        ("eggs", "protein", "fridge"),
        ("tomatoes", "vegetable", "room_temp"),
        ("greens", "vegetable", "fridge"),
        ("frozen dumplings", "frozen", "freezer"),
    ]
    for name, category, storage in pantry_patterns:
        if re.search(rf"\b{re.escape(name)}\b", normalized):
            pantry_items.append(
                PantryItem(
                    id=f"text_{name.replace(' ', '_')}",
                    name=name,
                    category=category,
                    storage=storage,
                    freshness="unknown",
                    source_type="mimo_mock",
                    source_ref="demo_text",
                    confidence=0.55,
                    notes="Extracted by mock text heuristic; please confirm before saving.",
                )
            )

    preferences = [
        LifePreference(
            domain="outfit",
            tags=["formal enough", "not flashy"],
            notes="Inferred from interview wording in mock text.",
        ),
        LifePreference(
            domain="cooking",
            tags=["family dinner", "quick"],
            notes="Inferred from dinner wording in mock text.",
        ),
    ]

    return LifeExtractionResult(
        source_id="demo_text",
        caption=text.strip() or None,
        wardrobe_items=wardrobe_items,
        pantry_items=pantry_items,
        preferences=preferences,
        low_confidence_notes=[
            "mock text heuristic extraction uses keyword rules; confirm assets before saving"
        ],
    )


def _with_mock_source(raw: dict[str, Any], source_id: str) -> dict[str, Any]:
    data = dict(raw)
    data.setdefault("source_type", "mimo_mock")
    data.setdefault("source_ref", source_id)
    return data


def _clean_source_id(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "mimo_mock"


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None
