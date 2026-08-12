# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Configured primary-user wardrobe lifecycle contracts."""

import pytest
from miloco.life.outfit_storage import OutfitStorage
from miloco.life.outfit_wardrobe import WardrobeDraftInput
from miloco.life.outfit_wardrobe_repo import OutfitWardrobeRepo
from miloco.life.outfit_wardrobe_service import OutfitWardrobeService


def _draft_input(
    *, source_reference: str = "navy shirt from closet"
) -> WardrobeDraftInput:
    return WardrobeDraftInput(
        name="navy cotton shirt",
        category="top",
        source_type="manual",
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


def test_confirming_an_exact_source_duplicate_preserves_existing_inventory(
    tmp_path,
) -> None:
    service = OutfitWardrobeService(
        OutfitWardrobeRepo(OutfitStorage(tmp_path / "outfit.db")),
        primary_person_id="primary-person",
        clock_ms=lambda: 2_000,
    )
    first = service.create_draft(_draft_input())
    service.confirm_draft(first.draft_id, confirmed_by_user=True)
    duplicate = service.create_draft(_draft_input())

    with pytest.raises(ValueError, match="duplicate wardrobe source"):
        service.confirm_draft(duplicate.draft_id, confirmed_by_user=True)

    assert len(service.list_confirmed_items()) == 1


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
