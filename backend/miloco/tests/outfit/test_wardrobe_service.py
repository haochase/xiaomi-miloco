# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Application-service contracts for the primary-user Outfit wardrobe."""

import sqlite3
from pathlib import Path

import pytest
from miloco.outfit.storage import OutfitStorage
from miloco.outfit.wardrobe import WardrobeSourceEvidence, confirm_wardrobe_draft
from miloco.outfit.wardrobe_repo import DuplicateWardrobeSourceError, WardrobeRepository
from miloco.outfit.wardrobe_service import WardrobeService


def _service(
    tmp_path: Path,
    *,
    primary_person_id: str = "primary-person",
    draft_id: str = "draft-navy-shirt",
) -> WardrobeService:
    return WardrobeService(
        WardrobeRepository(OutfitStorage(tmp_path / "outfit" / "wardrobe.db")),
        primary_person_id=primary_person_id,
        clock_ms=lambda: 1_700_000_000_100,
        draft_id_factory=lambda: draft_id,
    )


def _source(
    *,
    source_type: str = "manual",
    reference: str = "closet shelf A",
) -> tuple[WardrobeSourceEvidence, ...]:
    return (WardrobeSourceEvidence(source_type=source_type, reference=reference),)


def test_service_persists_pending_draft_and_confirms_only_for_primary_user(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)

    draft = service.create_draft(
        name="navy cotton shirt",
        category="top",
        source_evidence=_source(),
    )

    restarted_service = _service(tmp_path)

    assert draft.owner_person_id == "primary-person"
    assert restarted_service.list_pending_drafts() == (draft,)
    assert restarted_service.list_confirmed_available_items() == ()

    item = restarted_service.confirm_draft(draft.draft_id, confirmed_by_user=True)

    assert item.owner_person_id == "primary-person"
    assert restarted_service.list_pending_drafts() == ()
    assert restarted_service.list_confirmed_available_items() == (item,)


def test_service_requires_explicit_confirmation_before_inventory_changes(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    draft = service.create_draft(
        name="navy cotton shirt",
        category="top",
        source_evidence=_source(),
    )

    with pytest.raises(ValueError, match="explicit user confirmation"):
        service.confirm_draft(draft.draft_id, confirmed_by_user=False)

    assert service.list_pending_drafts() == (draft,)
    assert service.list_confirmed_available_items() == ()


def test_confirming_the_same_draft_again_returns_the_existing_item(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    draft = service.create_draft(
        name="navy cotton shirt",
        category="top",
        source_evidence=_source(),
    )

    first_confirmation = service.confirm_draft(
        draft.draft_id,
        confirmed_by_user=True,
    )

    assert (
        service.confirm_draft(draft.draft_id, confirmed_by_user=True)
        == first_confirmation
    )


def test_confirmation_rolls_back_item_when_draft_transition_fails(
    tmp_path: Path,
) -> None:
    storage = OutfitStorage(tmp_path / "outfit" / "wardrobe.db")
    repository = WardrobeRepository(storage)
    service = WardrobeService(
        repository,
        primary_person_id="primary-person",
        clock_ms=lambda: 1_700_000_000_100,
        draft_id_factory=lambda: "draft-atomic",
    )
    draft = service.create_draft(
        name="navy cotton shirt",
        category="top",
        source_evidence=_source(),
    )
    with storage.connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_draft_confirmation
            BEFORE UPDATE OF status ON outfit_wardrobe_drafts
            WHEN NEW.status = 'confirmed'
            BEGIN
                SELECT RAISE(ABORT, 'draft transition failed');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="draft transition failed"):
        service.confirm_draft(draft.draft_id, confirmed_by_user=True)

    assert service.list_pending_drafts() == (draft,)
    assert service.list_confirmed_available_items() == ()


def test_confirmation_retry_repairs_existing_item_pending_draft_split(
    tmp_path: Path,
) -> None:
    storage = OutfitStorage(tmp_path / "outfit" / "wardrobe.db")
    repository = WardrobeRepository(storage)
    service = WardrobeService(
        repository,
        primary_person_id="primary-person",
        clock_ms=lambda: 1_700_000_000_100,
        draft_id_factory=lambda: "draft-repair",
    )
    draft = service.create_draft(
        name="navy cotton shirt",
        category="top",
        source_evidence=_source(),
    )
    split_item = confirm_wardrobe_draft(
        draft,
        item_id=f"item-{draft.draft_id}",
        confirmed_at_ms=1_700_000_000_100,
        confirmed_by_user=True,
    )
    repository.add_confirmed_item(split_item)

    repaired = service.confirm_draft(draft.draft_id, confirmed_by_user=True)

    assert repaired == split_item
    assert service.list_pending_drafts() == ()
    assert service.list_confirmed_available_items() == (split_item,)


def test_confirmation_retry_rejects_same_id_with_different_item_content(
    tmp_path: Path,
) -> None:
    storage = OutfitStorage(tmp_path / "outfit" / "wardrobe.db")
    repository = WardrobeRepository(storage)
    service = WardrobeService(
        repository,
        primary_person_id="primary-person",
        clock_ms=lambda: 1_700_000_000_100,
        draft_id_factory=lambda: "draft-conflict",
    )
    draft = service.create_draft(
        name="navy cotton shirt",
        category="top",
        source_evidence=_source(),
    )
    conflicting_item = confirm_wardrobe_draft(
        draft,
        item_id=f"item-{draft.draft_id}",
        confirmed_at_ms=1_700_000_000_100,
        confirmed_by_user=True,
    ).model_copy(update={"name": "different item"})
    repository.add_confirmed_item(conflicting_item)

    with pytest.raises(ValueError, match="does not match pending draft"):
        service.confirm_draft(draft.draft_id, confirmed_by_user=True)

    assert service.list_pending_drafts() == (draft,)
    assert service.list_confirmed_available_items() == (conflicting_item,)


def test_duplicate_external_source_does_not_confirm_pending_draft(
    tmp_path: Path,
) -> None:
    first_service = _service(tmp_path, draft_id="draft-first")
    first = first_service.create_draft(
        name="navy cotton shirt",
        category="top",
        source_evidence=_source(
            source_type="photo",
            reference="media://photo/navy-shirt",
        ),
    )
    first_service.confirm_draft(first.draft_id, confirmed_by_user=True)

    second_service = _service(tmp_path, draft_id="draft-second")
    duplicate = second_service.create_draft(
        name="navy cotton shirt duplicate",
        category="top",
        source_evidence=_source(
            source_type="photo",
            reference="media://photo/navy-shirt",
        ),
    )

    with pytest.raises(DuplicateWardrobeSourceError, match="already confirmed"):
        second_service.confirm_draft(duplicate.draft_id, confirmed_by_user=True)

    assert second_service.list_pending_drafts() == (duplicate,)
    assert len(second_service.list_confirmed_available_items()) == 1


def test_service_rejects_blank_primary_person_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="primary_person_id must not be blank"):
        _service(tmp_path, primary_person_id="   ")
