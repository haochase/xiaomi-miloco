# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Fact-model contracts required by Outfit moment projections."""

import pytest
from miloco.life.outfit_feedback_events import OutfitFeedbackEvent
from pydantic import ValidationError


def test_wear_event_requires_explicit_user_confirmation_and_is_immutable() -> None:
    with pytest.raises(ValidationError, match="explicit user confirmation"):
        OutfitFeedbackEvent(
            event_id="wear-1",
            owner_person_id="owner-1",
            event_type="wear_confirmed",
            recommendation_id="recommendation-1",
            item_ids=("top-1", "bottom-1", "shoes-1"),
            occurred_at_ms=1000,
            confirmed_by_user=False,
        )

    event = OutfitFeedbackEvent(
        event_id="wear-1",
        owner_person_id="owner-1",
        event_type="wear_confirmed",
        recommendation_id="recommendation-1",
        item_ids=("top-1", "bottom-1", "shoes-1"),
        occurred_at_ms=1000,
        confirmed_by_user=True,
    )

    with pytest.raises(ValidationError):
        event.confirmed_by_user = False
