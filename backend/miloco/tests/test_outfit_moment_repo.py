# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""SQLite contract tests for owner-scoped Outfit moment projections."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from miloco.life.outfit_moment_repo import (
    OutfitMomentProjectionConflictError,
    OutfitMomentRepo,
)
from miloco.life.outfit_moments import OutfitMoment


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
        "user_note": "Confirmed before leaving.",
        "created_at_ms": 1001,
    }
    payload.update(changes)
    return OutfitMoment(**payload)


def test_repo_is_idempotent_per_owner_and_confirmed_wear(tmp_path: Path) -> None:
    repo = OutfitMomentRepo(tmp_path / "moments.db")
    moment = _moment()

    first = repo.save_or_get(moment)
    replayed = repo.save_or_get(
        moment.model_copy(update={"created_at_ms": moment.created_at_ms + 1})
    )

    assert replayed == first
    assert repo.get_for_owner("owner-1", "moment-wear-1") == first
    assert repo.list_for_owner("owner-1", limit=10) == [first]
    assert repo.list_for_owner("owner-2", limit=10) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timezone", "UTC"),
        ("recommendation_id", "recommendation-2"),
        ("item_ids", ("top-1", "bottom-1", "shoes-2")),
        ("source_event_ids", ("wear-1", "try-on-2")),
        ("user_note", "Changed after projection."),
        ("projection_version", 2),
    ],
)
def test_repo_rejects_changed_projection_inputs(
    tmp_path: Path, field: str, value: object
) -> None:
    repo = OutfitMomentRepo(tmp_path / "moments.db")
    moment = _moment()
    repo.save_or_get(moment)

    with pytest.raises(OutfitMomentProjectionConflictError):
        repo.save_or_get(moment.model_copy(update={field: value}))


def test_repo_allows_same_moment_id_for_different_owners(tmp_path: Path) -> None:
    repo = OutfitMomentRepo(tmp_path / "moments.db")
    first = repo.save_or_get(_moment())
    other_owner = _moment(owner_person_id="owner-2")

    second = repo.save_or_get(other_owner)

    assert first.owner_person_id == "owner-1"
    assert second.owner_person_id == "owner-2"
    assert repo.get_for_owner("owner-1", first.moment_id) == first
    assert repo.get_for_owner("owner-2", second.moment_id) == second


def test_concurrent_exact_replays_store_one_projection(tmp_path: Path) -> None:
    db_path = tmp_path / "moments.db"
    first_repo = OutfitMomentRepo(db_path)
    second_repo = OutfitMomentRepo(db_path)
    moment = _moment()
    barrier = Barrier(2)

    def save(repo: OutfitMomentRepo) -> OutfitMoment:
        barrier.wait()
        return repo.save_or_get(moment)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(save, (first_repo, second_repo)))

    assert first == second
    assert first_repo.list_for_owner("owner-1", limit=10) == [first]
