# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Life domain schema validation tests."""

import pytest
from miloco.life.schema import (
    CookingRecommendationRequest,
    LifePreference,
    PantryItem,
    RecommendationOption,
    RecommendationResult,
    WardrobeItem,
)
from pydantic import ValidationError


def test_wardrobe_item_validates_core_ranges_and_status():
    item = WardrobeItem(
        id="coat_1",
        name="  dark gray blazer  ",
        category="outerwear",
        colors=["gray", "black"],
        formality=4,
        warmth_level=3,
        source_type="manual",
        status="active",
        confidence=0.82,
    )

    assert item.name == "dark gray blazer"
    assert item.category == "outerwear"

    with pytest.raises(ValidationError):
        WardrobeItem(
            id="coat_1",
            name="dark gray blazer",
            category="outerwear",
            formality=6,
            warmth_level=3,
            source_type="manual",
            status="active",
            confidence=0.82,
        )

    with pytest.raises(ValidationError):
        WardrobeItem(
            id="coat_1",
            name="dark gray blazer",
            category="outerwear",
            formality=4,
            warmth_level=3,
            source_type="manual",
            status="clean",
            confidence=0.82,
        )


def test_pantry_item_validates_storage_freshness_and_confidence():
    item = PantryItem(
        id="egg_1",
        name="  eggs  ",
        category="protein",
        quantity=6,
        unit="pcs",
        storage="fridge",
        freshness="normal",
        source_type="mimo_mock",
        confidence=0.7,
    )

    assert item.name == "eggs"
    assert item.storage == "fridge"

    with pytest.raises(ValidationError):
        PantryItem(
            id="egg_1",
            name="eggs",
            category="protein",
            storage="fridge",
            freshness="normal",
            source_type="mimo_mock",
            confidence=1.2,
        )

    with pytest.raises(ValidationError):
        PantryItem(
            id="egg_1",
            name="eggs",
            category="protein",
            storage="garage",
            freshness="normal",
            source_type="mimo_mock",
            confidence=0.7,
        )


def test_preference_normalizes_blank_notes_and_tags():
    preference = LifePreference(
        person_id="person_a",
        domain="outfit",
        tags=["  formal ", "", "warm"],
        notes="   ",
    )

    assert preference.tags == ["formal", "warm"]
    assert preference.notes is None


def test_optional_person_refs_normalize_blank_values():
    wardrobe_item = WardrobeItem(
        id="coat_1",
        owner_person_id="   ",
        name="dark gray blazer",
        category="outerwear",
        formality=4,
        warmth_level=3,
        source_type="manual",
        status="active",
        confidence=0.82,
    )
    preference = LifePreference(
        person_id="  person_a  ",
        domain="outfit",
    )

    assert wardrobe_item.owner_person_id is None
    assert preference.person_id == "person_a"


def test_cooking_request_requires_positive_people_and_minutes():
    request = CookingRecommendationRequest(
        pantry_item_ids=["egg_1", "tomato_1"],
        people_count=3,
        time_budget_minutes=30,
        taste_tags=["light"],
    )

    assert request.people_count == 3

    with pytest.raises(ValidationError):
        CookingRecommendationRequest(
            pantry_item_ids=["egg_1"],
            people_count=0,
            time_budget_minutes=30,
        )

    with pytest.raises(ValidationError):
        CookingRecommendationRequest(
            pantry_item_ids=["egg_1"],
            people_count=3,
            time_budget_minutes=0,
        )


def test_recommendation_item_ids_reject_blank_refs():
    with pytest.raises(ValidationError):
        CookingRecommendationRequest(
            pantry_item_ids=["egg_1", "  "],
            people_count=3,
            time_budget_minutes=30,
        )

    with pytest.raises(ValidationError):
        RecommendationOption(
            title="tomato eggs",
            summary="Cook a light dinner in about 30 minutes.",
            item_ids=["egg_1", ""],
        )


def test_cooking_recommendation_rejects_absolute_safety_claims():
    option = RecommendationOption(
        title="tomato eggs with greens",
        summary="Cook a light dinner in about 30 minutes.",
        rationale=["uses existing eggs", "keeps prep simple"],
        item_ids=["egg_1", "tomato_1"],
        safety_notes=[
            "The water may be boiling; please confirm before adding dumplings."
        ],
    )
    result = RecommendationResult(domain="cooking", options=[option])

    assert result.domain == "cooking"

    with pytest.raises(ValidationError):
        RecommendationOption(
            title="unsafe kitchen advice",
            summary="Turn off the stove.",
            rationale=["timer ended"],
            item_ids=["egg_1"],
            safety_notes=["Food is fully cooked and safety is confirmed."],
        )


def test_cooking_recommendation_rejects_chinese_absolute_safety_claims():
    with pytest.raises(ValidationError):
        RecommendationOption(
            title="厨房提醒",
            summary="已经熟了，可以吃了。",
            rationale=["timer ended"],
            item_ids=["dumpling_1"],
            safety_notes=["我确认安全。"],
        )


def test_cooking_result_rejects_absolute_broadcast_safety_claims():
    option = RecommendationOption(
        title="tomato eggs with greens",
        summary="Cook a light dinner in about 30 minutes.",
        safety_notes=[
            "The water may be boiling; please confirm before adding dumplings."
        ],
    )

    with pytest.raises(ValidationError):
        RecommendationResult(
            domain="cooking",
            options=[option],
            broadcast_text="Dumplings are fully cooked and safety is confirmed.",
        )
