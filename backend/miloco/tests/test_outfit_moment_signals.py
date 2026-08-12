# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Deterministic evidence signals for reviewable Outfit moment tags."""

import pytest
from miloco.life.outfit_moment_signals import derive_moment_signals
from miloco.life.outfit_moments import OutfitMoment, OutfitMomentTag
from pydantic import ValidationError


def _moment(
    event_id: str,
    occurred_at_ms: int,
    *,
    colors: tuple[str, ...] = (),
) -> OutfitMoment:
    return OutfitMoment(
        moment_id=f"moment-{event_id}",
        owner_person_id="owner-1",
        occurred_at_ms=occurred_at_ms,
        timezone="Asia/Shanghai",
        recommendation_id=f"recommendation-{event_id}",
        confirmed_wear_event_id=event_id,
        item_ids=("top-1", "bottom-1", "shoes-1"),
        color_labels=colors,
        source_event_ids=(event_id,),
        created_at_ms=occurred_at_ms + 1,
    )


def test_repeat_favorite_requires_three_confirmed_moments() -> None:
    first = _moment("wear-1", 1_000)
    second = _moment("wear-2", 2_000)
    current = _moment("wear-3", 3_000)

    signals = derive_moment_signals(current, history=[first, second, current])
    repeat = next(
        signal for signal in signals if signal.signal_type == "repeat_favorite"
    )

    assert repeat.value_json == {"confirmed_count": 3}
    assert repeat.evidence_event_ids == ("wear-1", "wear-2", "wear-3")


def test_rare_color_return_uses_confirmed_metadata_and_a_fixed_time_window() -> None:
    thirty_one_days_ms = 31 * 24 * 60 * 60 * 1000
    first = _moment("wear-1", 1_000, colors=("red",))
    current = _moment("wear-2", 1_000 + thirty_one_days_ms, colors=("red",))

    signals = derive_moment_signals(current, history=[first, current])
    returned = next(
        signal for signal in signals if signal.signal_type == "rare_color_return"
    )

    assert returned.value_json == {
        "color": "red",
        "days_since_last_confirmed": 31,
    }
    assert returned.evidence_event_ids == ("wear-1", "wear-2")


def test_system_tags_reject_sensitive_inference_language() -> None:
    with pytest.raises(ValidationError, match="sensitive inference"):
        OutfitMomentTag(
            tag_id="tag-1",
            moment_id="moment-1",
            tag_type="repeat_favorite",
            label="Mood diagnosis",
            narrative="This means anxiety.",
            evidence_signal_ids=("signal-1",),
            source="rule",
            confidence=1,
            review_status="pending",
            dedupe_key="repeat:moment-1",
            generator_version="rule-v1",
        )
