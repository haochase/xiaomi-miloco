# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Projection service contracts for confirmed Outfit wear facts."""

from pathlib import Path

import pytest
from miloco.life.outfit_feedback_event_repo import OutfitFeedbackEventRepo
from miloco.life.outfit_feedback_events import OutfitFeedbackEvent
from miloco.life.outfit_moment_repo import OutfitMomentRepo
from miloco.life.outfit_moment_service import OutfitMomentService
from miloco.life.outfit_moments import OutfitMoment


def _confirmed_wear() -> OutfitFeedbackEvent:
    return OutfitFeedbackEvent(
        event_id="wear-1",
        owner_person_id="owner-1",
        event_type="wear_confirmed",
        recommendation_id="recommendation-1",
        item_ids=("top-1", "bottom-1", "shoes-1"),
        occurred_at_ms=1000,
        confirmed_by_user=True,
    )


def test_projection_loads_persisted_confirmed_wear_instead_of_client_facts(
    tmp_path: Path,
) -> None:
    event_repo = OutfitFeedbackEventRepo(tmp_path / "events.db")
    moment_repo = OutfitMomentRepo(tmp_path / "moments.db")
    confirmed_wear = _confirmed_wear()
    event_repo.append(confirmed_wear)
    service = OutfitMomentService(event_repo, moment_repo, clock_ms=lambda: 2000)

    result = service.project_confirmed_wear(
        event_id="wear-1",
        owner_person_id="owner-1",
        timezone="Asia/Shanghai",
    )

    assert result.item_ids == confirmed_wear.item_ids
    assert result.confirmed_wear_event_id == "wear-1"
    assert result.created_at_ms == 2000


def test_projection_rejects_missing_or_foreign_event(tmp_path: Path) -> None:
    event_repo = OutfitFeedbackEventRepo(tmp_path / "events.db")
    moment_repo = OutfitMomentRepo(tmp_path / "moments.db")
    event_repo.append(_confirmed_wear())
    service = OutfitMomentService(event_repo, moment_repo, clock_ms=lambda: 2000)

    with pytest.raises(ValueError, match="not found"):
        service.project_confirmed_wear(
            event_id="wear-1",
            owner_person_id="owner-2",
            timezone="Asia/Shanghai",
        )


def test_rejected_tag_dedupe_key_is_not_proposed_again(tmp_path: Path) -> None:
    event_repo = OutfitFeedbackEventRepo(tmp_path / "events.db")
    moment_repo = OutfitMomentRepo(tmp_path / "moments.db")
    service = OutfitMomentService(event_repo, moment_repo, clock_ms=lambda: 4000)
    moments = [
        OutfitMoment(
            moment_id=f"moment-wear-{index}",
            owner_person_id="owner-1",
            occurred_at_ms=index * 1000,
            timezone="Asia/Shanghai",
            recommendation_id=f"recommendation-{index}",
            confirmed_wear_event_id=f"wear-{index}",
            item_ids=("top-1", "bottom-1", "shoes-1"),
            source_event_ids=(f"wear-{index}",),
            created_at_ms=index * 1000 + 1,
        )
        for index in range(1, 4)
    ]
    for moment in moments:
        moment_repo.save_or_get(moment)

    proposed = service.refresh_tags("moment-wear-3", owner_person_id="owner-1")
    repeat = next(tag for tag in proposed if tag.tag_type == "repeat_favorite")
    rejected = service.reject_tag(repeat.tag_id, owner_person_id="owner-1")
    refreshed = service.refresh_tags("moment-wear-3", owner_person_id="owner-1")

    assert rejected.review_status == "rejected"
    assert rejected.dedupe_key not in {tag.dedupe_key for tag in refreshed}
