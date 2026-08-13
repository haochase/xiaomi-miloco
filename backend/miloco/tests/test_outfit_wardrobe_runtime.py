# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Configured primary-user wardrobe lifecycle contracts."""

import pytest
from miloco.life.outfit_storage import OutfitStorage
from miloco.life.outfit_wardrobe import ConfirmedWardrobeItem, WardrobeDraftInput
from miloco.life.outfit_wardrobe_repo import OutfitWardrobeRepo
from miloco.life.outfit_wardrobe_service import OutfitWardrobeService


def _draft_input(
    *,
    name: str = "navy cotton shirt",
    source_type: str = "manual",
    source_reference: str = "navy shirt from closet",
) -> WardrobeDraftInput:
    return WardrobeDraftInput(
        name=name,
        category="top",
        source_type=source_type,
        source_reference=source_reference,
    )


def test_pending_draft_does_not_enter_primary_user_inventory_before_confirmation(
    tmp_path,
) -> None:
    service = OutfitWardrobeService(
        OutfitWardrobeRepo(OutfitStorage(tmp_path / "outfit.db")),
        primary_person_id="primary-person",
        clock_ms=lambda: 2_000,
    )

    draft = service.create_draft(_draft_input())

    assert draft.owner_person_id == "primary-person"
    assert draft.status == "pending"
    assert service.list_confirmed_items() == []

    item = service.confirm_draft(draft.draft_id, confirmed_by_user=True)

    assert item.owner_person_id == "primary-person"
    assert item.name == "navy cotton shirt"
    assert [stored.item_id for stored in service.list_confirmed_items()] == [
        item.item_id
    ]


@pytest.mark.parametrize(
    ("source_type", "source_reference"),
    [
        ("photo", "sha256:outfit-photo-1"),
        ("product_link", "https://shop.example.test/products/navy-shirt"),
    ],
)
def test_confirming_an_exact_external_source_duplicate_preserves_existing_inventory(
    tmp_path,
    source_type: str,
    source_reference: str,
) -> None:
    service = OutfitWardrobeService(
        OutfitWardrobeRepo(OutfitStorage(tmp_path / "outfit.db")),
        primary_person_id="primary-person",
        clock_ms=lambda: 2_000,
    )
    input = _draft_input(
        source_type=source_type,
        source_reference=source_reference,
    )
    first = service.create_draft(input)
    service.confirm_draft(first.draft_id, confirmed_by_user=True)
    duplicate = service.create_draft(input)

    with pytest.raises(ValueError, match="duplicate wardrobe source"):
        service.confirm_draft(duplicate.draft_id, confirmed_by_user=True)

    assert len(service.list_confirmed_items()) == 1


def test_manual_items_can_share_the_same_storage_location(tmp_path) -> None:
    service = OutfitWardrobeService(
        OutfitWardrobeRepo(OutfitStorage(tmp_path / "outfit.db")),
        primary_person_id="primary-person",
        clock_ms=lambda: 2_000,
    )
    first = service.create_draft(
        _draft_input(name="navy cotton shirt", source_reference="closet")
    )
    second = service.create_draft(
        _draft_input(name="white cotton t-shirt", source_reference="closet")
    )

    first_item = service.confirm_draft(first.draft_id, confirmed_by_user=True)
    second_item = service.confirm_draft(second.draft_id, confirmed_by_user=True)

    assert {item.name for item in service.list_confirmed_items()} == {
        first_item.name,
        second_item.name,
    }


def test_repository_migrates_legacy_manual_source_constraint(tmp_path) -> None:
    storage = OutfitStorage(tmp_path / "outfit.db")
    existing_item = ConfirmedWardrobeItem(
        item_id="item-legacy-shirt",
        owner_person_id="primary-person",
        name="legacy navy shirt",
        category="top",
        source_type="manual",
        source_reference="closet",
        confirmed_at_ms=1_000,
    )
    with storage.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE outfit_wardrobe_item (
                owner_person_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                confirmed_at_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (owner_person_id, item_id),
                UNIQUE (owner_person_id, source_type, source_reference)
            );

            CREATE INDEX idx_outfit_wardrobe_item_owner
            ON outfit_wardrobe_item(owner_person_id);
            """
        )
        conn.execute(
            """
            INSERT INTO outfit_wardrobe_item (
                owner_person_id,
                item_id,
                source_type,
                source_reference,
                confirmed_at_ms,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                existing_item.owner_person_id,
                existing_item.item_id,
                existing_item.source_type,
                existing_item.source_reference,
                existing_item.confirmed_at_ms,
                existing_item.model_dump_json(),
            ),
        )

    service = OutfitWardrobeService(
        OutfitWardrobeRepo(storage),
        primary_person_id="primary-person",
        clock_ms=lambda: 2_000,
    )
    new_draft = service.create_draft(
        _draft_input(name="new white t-shirt", source_reference="closet")
    )

    service.confirm_draft(new_draft.draft_id, confirmed_by_user=True)

    assert [item.name for item in service.list_confirmed_items()] == [
        "legacy navy shirt",
        "new white t-shirt",
    ]
    with storage.connect() as conn:
        index_names = {
            row["name"]
            for row in conn.execute("PRAGMA index_list('outfit_wardrobe_item')")
        }
    assert index_names >= {
        "idx_outfit_wardrobe_item_owner",
        "idx_outfit_wardrobe_item_external_source",
    }


def test_reconfirming_the_same_draft_returns_the_original_inventory_item(
    tmp_path,
) -> None:
    service = OutfitWardrobeService(
        OutfitWardrobeRepo(OutfitStorage(tmp_path / "outfit.db")),
        primary_person_id="primary-person",
        clock_ms=lambda: 2_000,
    )
    draft = service.create_draft(_draft_input())

    first = service.confirm_draft(draft.draft_id, confirmed_by_user=True)
    replayed = service.confirm_draft(draft.draft_id, confirmed_by_user=True)

    assert replayed == first
    assert [item.item_id for item in service.list_confirmed_items()] == [first.item_id]


def test_user_can_discard_a_pending_draft_without_affecting_inventory(tmp_path) -> None:
    service = OutfitWardrobeService(
        OutfitWardrobeRepo(OutfitStorage(tmp_path / "outfit.db")),
        primary_person_id="primary-person",
        clock_ms=lambda: 2_000,
    )
    draft = service.create_draft(_draft_input())

    assert service.list_pending_drafts() == [draft]
    service.discard_draft(draft.draft_id, confirmed_by_user=True)

    assert service.list_pending_drafts() == []
    assert service.list_confirmed_items() == []


def test_user_can_correct_or_delete_a_confirmed_item_without_mutating_its_source(
    tmp_path,
) -> None:
    service = OutfitWardrobeService(
        OutfitWardrobeRepo(OutfitStorage(tmp_path / "outfit.db")),
        primary_person_id="primary-person",
        clock_ms=lambda: 2_000,
    )
    draft = service.create_draft(_draft_input())
    item = service.confirm_draft(draft.draft_id, confirmed_by_user=True)

    updated = service.update_item(
        item.item_id,
        name="navy linen shirt",
        category="outerwear",
    )
    service.delete_item(item.item_id, confirmed_by_user=True)

    assert updated.name == "navy linen shirt"
    assert updated.category == "outerwear"
    assert updated.source_reference == "navy shirt from closet"
    assert service.list_confirmed_items() == []
