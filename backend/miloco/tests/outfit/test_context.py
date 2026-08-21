# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Structured scenario contracts for deterministic Outfit recommendations."""

import pytest
from miloco.outfit.context import OutfitRecommendationContext, next_clarification
from pydantic import ValidationError


def test_explicit_occasion_needs_no_clarification() -> None:
    context = OutfitRecommendationContext(
        occasion="client meeting",
        day_kind="workday",
    )

    assert next_clarification(context) is None


def test_missing_occasion_and_activity_requests_one_scene_question() -> None:
    clarification = next_clarification(OutfitRecommendationContext())

    assert clarification.field == "occasion_or_activity"
    assert (
        clarification.prompt == "What occasion or activity should this outfit support?"
    )


def test_context_rejects_request_controlled_owner_selector() -> None:
    with pytest.raises(ValidationError, match="owner_person_id"):
        OutfitRecommendationContext.model_validate(
            {"owner_person_id": "untrusted-request-owner"},
        )
