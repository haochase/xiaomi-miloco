# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Persistence contracts for private, owner-scoped Outfit recommendation snapshots."""

from pathlib import Path

import pytest
from miloco.outfit.context import OutfitRecommendationContext
from miloco.outfit.recommendation_api import RecommendationSnapshot
from miloco.outfit.recommendation_snapshot_repo import (
    RecommendationSnapshotConflictError,
    RecommendationSnapshotRepository,
)
from miloco.outfit.storage import OutfitStorage


def _repository(tmp_path: Path) -> RecommendationSnapshotRepository:
    return RecommendationSnapshotRepository(
        OutfitStorage(tmp_path / "outfit" / "wardrobe.db")
    )


def _snapshot(
    *,
    snapshot_id: str = "rec-snapshot-1",
    created_at_ms: int = 1_000,
) -> RecommendationSnapshot:
    return RecommendationSnapshot(
        snapshot_id=snapshot_id,
        context=OutfitRecommendationContext(occasion="commute"),
        status="ready",
        option_item_ids=(
            ("item-top", "item-bottom", "item-shoes"),
            ("item-dress", "item-shoes"),
        ),
        ranking_version="deterministic-v1",
        created_at_ms=created_at_ms,
    )


def test_save_is_idempotent_and_reads_only_for_the_same_owner(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    snapshot = _snapshot()

    repository.save(
        owner_person_id="primary-owner",
        snapshot=snapshot,
        expires_at_ms=1_000 + 86_400_000,
    )
    repository.save(
        owner_person_id="primary-owner",
        snapshot=snapshot,
        expires_at_ms=1_000 + 86_400_000,
    )

    assert (
        repository.get_active(
            owner_person_id="primary-owner",
            snapshot_id="rec-snapshot-1",
            now_ms=1_001,
        )
        == snapshot
    )
    assert (
        repository.get_active(
            owner_person_id="other-owner",
            snapshot_id="rec-snapshot-1",
            now_ms=1_001,
        )
        is None
    )


def test_same_owner_snapshot_id_rejects_changed_payload(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.save(
        owner_person_id="primary-owner",
        snapshot=_snapshot(),
        expires_at_ms=87_400_000,
    )

    with pytest.raises(RecommendationSnapshotConflictError):
        repository.save(
            owner_person_id="primary-owner",
            snapshot=_snapshot(created_at_ms=1_001),
            expires_at_ms=87_400_001,
        )


def test_same_snapshot_payload_rejects_changed_expiry_for_the_same_owner(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    snapshot = _snapshot()
    repository.save(
        owner_person_id="primary-owner",
        snapshot=snapshot,
        expires_at_ms=87_400_000,
    )

    with pytest.raises(RecommendationSnapshotConflictError):
        repository.save(
            owner_person_id="primary-owner",
            snapshot=snapshot,
            expires_at_ms=87_400_001,
        )


def test_snapshot_id_identity_is_scoped_to_owner(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    first = _snapshot()
    second = _snapshot(created_at_ms=1_001)

    repository.save(
        owner_person_id="primary-owner",
        snapshot=first,
        expires_at_ms=87_400_000,
    )
    repository.save(
        owner_person_id="other-owner",
        snapshot=second,
        expires_at_ms=87_400_001,
    )

    assert (
        repository.get_active(
            owner_person_id="primary-owner",
            snapshot_id=first.snapshot_id,
            now_ms=1_002,
        )
        == first
    )
    assert (
        repository.get_active(
            owner_person_id="other-owner",
            snapshot_id=second.snapshot_id,
            now_ms=1_002,
        )
        == second
    )


def test_expired_snapshot_is_not_readable_and_purge_removes_it(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    snapshot = _snapshot()
    repository.save(
        owner_person_id="primary-owner",
        snapshot=snapshot,
        expires_at_ms=1_000 + 86_400_000,
    )

    assert (
        repository.get_active(
            owner_person_id="primary-owner",
            snapshot_id=snapshot.snapshot_id,
            now_ms=1_000 + 86_400_000 - 1,
        )
        == snapshot
    )
    assert (
        repository.get_active(
            owner_person_id="primary-owner",
            snapshot_id=snapshot.snapshot_id,
            now_ms=1_000 + 86_400_000,
        )
        is None
    )
    assert repository.purge_expired(now_ms=1_000 + 86_400_000) == 1
    assert (
        repository.get_active(
            owner_person_id="primary-owner",
            snapshot_id=snapshot.snapshot_id,
            now_ms=1_000 + 86_400_001,
        )
        is None
    )


def test_save_rejects_expiry_before_or_at_snapshot_creation(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    snapshot = _snapshot()

    with pytest.raises(ValueError, match="expires_at_ms"):
        repository.save(
            owner_person_id="primary-owner",
            snapshot=snapshot,
            expires_at_ms=snapshot.created_at_ms,
        )


@pytest.mark.parametrize("invalid_epoch_ms", [True, -1, 1.5, float("inf"), "100"])
def test_repository_rejects_invalid_epoch_milliseconds(
    tmp_path: Path,
    invalid_epoch_ms: object,
) -> None:
    repository = _repository(tmp_path)
    snapshot = _snapshot()

    with pytest.raises(ValueError, match="epoch milliseconds"):
        repository.save(
            owner_person_id="primary-owner",
            snapshot=snapshot,
            expires_at_ms=invalid_epoch_ms,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="epoch milliseconds"):
        repository.get_active(
            owner_person_id="primary-owner",
            snapshot_id=snapshot.snapshot_id,
            now_ms=invalid_epoch_ms,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="epoch milliseconds"):
        repository.purge_expired(now_ms=invalid_epoch_ms)  # type: ignore[arg-type]


def test_snapshot_table_has_owner_scoped_key_and_no_sensitive_columns(
    tmp_path: Path,
) -> None:
    storage = OutfitStorage(tmp_path / "outfit" / "wardrobe.db")
    RecommendationSnapshotRepository(storage)

    with storage.connect() as connection:
        columns = connection.execute(
            "PRAGMA table_info(outfit_recommendation_snapshots)"
        ).fetchall()

    assert [(row["name"], row["pk"]) for row in columns if row["pk"]] == [
        ("owner_person_id", 1),
        ("snapshot_id", 2),
    ]
    assert {row["name"] for row in columns}.isdisjoint(
        {
            "raw_media",
            "media_path",
            "source_reference",
            "model_response",
            "owner_name",
        }
    )
