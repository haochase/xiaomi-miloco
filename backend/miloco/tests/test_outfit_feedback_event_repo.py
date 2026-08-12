# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Owner-scoped lookup contracts for immutable Outfit feedback events."""

from pathlib import Path

import pytest
from miloco.life.outfit_feedback_event_repo import (
    OutfitFeedbackEventConflictError,
    OutfitFeedbackEventRepo,
)
from miloco.life.outfit_feedback_events import OutfitFeedbackEvent


def _event(
    event_id: str,
    *,
    owner_person_id: str = "owner-1",
    occurred_at_ms: int = 1000,
) -> OutfitFeedbackEvent:
    return OutfitFeedbackEvent(
        event_id=event_id,
        owner_person_id=owner_person_id,
        event_type="wear_confirmed",
        recommendation_id="recommendation-1",
        item_ids=("top-1", "bottom-1", "shoes-1"),
        occurred_at_ms=occurred_at_ms,
        confirmed_by_user=True,
    )


def test_event_repo_returns_event_only_to_its_owner(tmp_path: Path) -> None:
    repo = OutfitFeedbackEventRepo(tmp_path / "events.db")
    event = _event("wear-1")
    repo.append(event)

    assert repo.get_for_owner("wear-1", "owner-1") == event
    assert repo.get_for_owner("wear-1", "owner-2") is None


def test_event_repo_replays_owner_events_in_timestamp_order(tmp_path: Path) -> None:
    repo = OutfitFeedbackEventRepo(tmp_path / "events.db")
    repo.append(_event("wear-later", occurred_at_ms=2000))
    repo.append(_event("wear-earlier", occurred_at_ms=1000))

    assert [event.event_id for event in repo.list_for_owner("owner-1")] == [
        "wear-earlier",
        "wear-later",
    ]
    assert repo.append(_event("wear-earlier", occurred_at_ms=1000)) == _event(
        "wear-earlier", occurred_at_ms=1000
    )


def test_event_repo_partitions_identical_event_ids_by_owner(tmp_path: Path) -> None:
    repo = OutfitFeedbackEventRepo(tmp_path / "events.db")
    first = _event("wear-1", owner_person_id="owner-1")
    second = _event("wear-1", owner_person_id="owner-2")

    assert repo.append(first) == first
    assert repo.append(second) == second
    assert repo.get_for_owner("wear-1", "owner-1") == first
    assert repo.get_for_owner("wear-1", "owner-2") == second


def test_event_repo_rejects_changed_payload_for_an_event_replay(tmp_path: Path) -> None:
    repo = OutfitFeedbackEventRepo(tmp_path / "events.db")
    stored = _event("wear-1")
    repo.append(stored)

    with pytest.raises(OutfitFeedbackEventConflictError):
        repo.append(_event("wear-1", occurred_at_ms=2000))
