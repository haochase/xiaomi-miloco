# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""SQLite repository contracts for confirmed Outfit wardrobe items."""

from pathlib import Path

import pytest
from miloco.outfit.storage import OutfitStorage
from miloco.outfit.wardrobe import ConfirmedWardrobeItem, WardrobeSourceEvidence
from miloco.outfit.wardrobe_repo import (
    DuplicateWardrobeSourceError,
    WardrobeRepository,
)


def _item(
    *,
    item_id: str,
    owner_person_id: str = "primary-person",
    source_type: str = "manual",
    source_reference: str = "closet shelf A",
    availability: str = "available",
) -> ConfirmedWardrobeItem:
    return ConfirmedWardrobeItem(
        item_id=item_id,
        owner_person_id=owner_person_id,
        name=f"item {item_id}",
        category="top",
        source_evidence=[
            WardrobeSourceEvidence(
                source_type=source_type,
                reference=source_reference,
            )
        ],
        confirmed_at_ms=1_700_000_000_100,
        confirmed_by_user=True,
        availability=availability,
    )


def _repository(tmp_path: Path) -> WardrobeRepository:
    return WardrobeRepository(OutfitStorage(tmp_path / "outfit" / "wardrobe.db"))


def test_repository_persists_confirmed_item_across_repository_instances(
    tmp_path: Path,
) -> None:
    storage = OutfitStorage(tmp_path / "outfit" / "wardrobe.db")
    item = _item(item_id="navy-shirt")

    WardrobeRepository(storage).add_confirmed_item(item)

    assert WardrobeRepository(storage).list_confirmed_available_items(
        "primary-person"
    ) == (item,)


def test_confirmed_available_query_is_scoped_to_owner_and_availability(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    primary_item = _item(item_id="navy-shirt")
    other_owner_item = _item(item_id="other-shirt", owner_person_id="other-person")
    laundry_item = _item(item_id="laundry-shirt", availability="laundry")

    repository.add_confirmed_item(primary_item)
    repository.add_confirmed_item(other_owner_item)
    repository.add_confirmed_item(laundry_item)

    assert repository.list_confirmed_available_items("primary-person") == (
        primary_item,
    )


def test_repository_rejects_duplicate_exact_external_source_for_same_owner(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    repository.add_confirmed_item(
        _item(
            item_id="navy-shirt",
            source_type="photo",
            source_reference="media://photo/navy-shirt",
        )
    )

    with pytest.raises(DuplicateWardrobeSourceError, match="already confirmed"):
        repository.add_confirmed_item(
            _item(
                item_id="duplicate-navy-shirt",
                source_type="photo",
                source_reference="media://photo/navy-shirt",
            )
        )


def test_repository_allows_same_manual_note_for_distinct_items(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    first = _item(item_id="navy-shirt")
    second = _item(item_id="white-shirt")

    repository.add_confirmed_item(first)
    repository.add_confirmed_item(second)

    assert repository.list_confirmed_available_items("primary-person") == (
        first,
        second,
    )


def test_external_source_deduplication_does_not_cross_owner_boundaries(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    source_reference = "https://example.test/products/navy-shirt"
    primary_item = _item(
        item_id="primary-shirt",
        source_type="product_link",
        source_reference=source_reference,
    )
    other_owner_item = _item(
        item_id="other-shirt",
        owner_person_id="other-person",
        source_type="product_link",
        source_reference=source_reference,
    )

    repository.add_confirmed_item(primary_item)
    repository.add_confirmed_item(other_owner_item)

    assert repository.list_confirmed_available_items("other-person") == (
        other_owner_item,
    )


def test_new_schema_uses_owner_scoped_identity_keys_and_foreign_key(
    tmp_path: Path,
) -> None:
    storage = OutfitStorage(tmp_path / "outfit" / "wardrobe.db")
    WardrobeRepository(storage)

    with storage.connect() as connection:
        item_columns = connection.execute(
            "PRAGMA table_info(outfit_confirmed_wardrobe_items)"
        ).fetchall()
        draft_columns = connection.execute(
            "PRAGMA table_info(outfit_wardrobe_drafts)"
        ).fetchall()
        external_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(outfit_confirmed_wardrobe_external_sources)"
        ).fetchall()

    assert [(row["name"], row["pk"]) for row in item_columns if row["pk"]] == [
        ("owner_person_id", 1),
        ("item_id", 2),
    ]
    assert [(row["name"], row["pk"]) for row in draft_columns if row["pk"]] == [
        ("owner_person_id", 1),
        ("draft_id", 2),
    ]
    assert sorted(
        (row["seq"], row["from"], row["to"])
        for row in external_foreign_keys
        if row["table"] == "outfit_confirmed_wardrobe_items"
    ) == [
        (0, "owner_person_id", "owner_person_id"),
        (1, "item_id", "item_id"),
    ]


def test_repository_has_no_standalone_non_atomic_draft_transition(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)

    assert not hasattr(repository, "mark_draft_confirmed")
