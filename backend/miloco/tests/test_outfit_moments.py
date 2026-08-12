# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Contract tests for immutable Outfit moment projections."""

from __future__ import annotations

import pytest
from miloco.life.outfit_moments import OutfitMoment, OutfitMomentTag


def _moment(**changes: object) -> OutfitMoment:
    payload: dict[str, object] = {
        "moment_id": "moment-wear-1",
        "owner_person_id": "owner-1",
        "occurred_at_ms": 1000,
        "timezone": "Asia/Shanghai",
        "recommendation_id": "recommendation-1",
        "confirmed_wear_event_id": "wear-1",
        "item_ids": ("top-1", "bottom-1", "shoes-1"),
        "source_event_ids": ("recommendation-presented-1", "wear-1"),
        "created_at_ms": 1001,
    }
    payload.update(changes)
    return OutfitMoment(**payload)


def test_moment_requires_confirmed_wear_event_reference() -> None:
    with pytest.raises(ValueError, match="confirmed wear event"):
        _moment(confirmed_wear_event_id="")


def test_moment_requires_confirmed_wear_event_in_sources() -> None:
    with pytest.raises(ValueError, match="source events must contain"):
        _moment(source_event_ids=("recommendation-presented-1",))


def test_moment_requires_confirmed_worn_items() -> None:
    with pytest.raises(ValueError, match="confirmed worn items"):
        _moment(item_ids=())


def test_system_tag_requires_evidence_signal() -> None:
    with pytest.raises(ValueError, match="system tags require"):
        OutfitMomentTag(
            tag_id="tag-1",
            moment_id="moment-wear-1",
            tag_type="rare_color_return",
            label="Bright color return",
            narrative="This label has explicit historical evidence.",
            evidence_signal_ids=(),
            source="rule",
            confidence=0.8,
            review_status="pending",
            dedupe_key="rare-color-return:v1",
            generator_version="rule-v1",
        )


def test_user_tag_can_be_evidence_free() -> None:
    tag = OutfitMomentTag(
        tag_id="tag-user-1",
        moment_id="moment-wear-1",
        tag_type="user_defined",
        label="Wanted this outfit",
        narrative="A note entered directly by the user.",
        evidence_signal_ids=(),
        source="user",
        confidence=1.0,
        review_status="confirmed",
        dedupe_key="user:tag-user-1",
        generator_version="user-v1",
    )

    assert tag.source == "user"
    assert _moment().model_dump()["confirmed_wear_event_id"] == "wear-1"
