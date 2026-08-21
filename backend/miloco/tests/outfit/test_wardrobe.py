# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Pure primary-user wardrobe contracts for the Outfit plugin."""

import pytest
from miloco.outfit.wardrobe import (
    ConfirmedWardrobeItem,
    WardrobeItemDraft,
    WardrobeSourceEvidence,
    confirm_wardrobe_draft,
    has_exact_external_source_duplicate,
)
from pydantic import ValidationError


def _draft(
    *,
    source_type: str = "manual",
    source_reference: str = "closet shelf A",
) -> WardrobeItemDraft:
    return WardrobeItemDraft(
        draft_id="draft-navy-shirt",
        owner_person_id="primary-person",
        name="  navy cotton shirt  ",
        category="top",
        source_evidence=[
            WardrobeSourceEvidence(
                source_type=source_type,
                reference=source_reference,
            )
        ],
        created_at_ms=1_700_000_000_000,
    )


def test_draft_is_pending_and_preserves_normalized_source_evidence():
    draft = _draft()

    assert draft.status == "pending"
    assert draft.name == "navy cotton shirt"
    assert draft.owner_person_id == "primary-person"
    assert draft.source_evidence == (
        WardrobeSourceEvidence(source_type="manual", reference="closet shelf A"),
    )


def test_draft_cannot_be_represented_as_a_confirmed_item():
    with pytest.raises(ValidationError, match="pending"):
        WardrobeItemDraft(
            draft_id="draft-navy-shirt",
            owner_person_id="primary-person",
            name="navy cotton shirt",
            category="top",
            source_evidence=[
                WardrobeSourceEvidence(
                    source_type="manual",
                    reference="closet shelf A",
                )
            ],
            created_at_ms=1_700_000_000_000,
            status="confirmed",
        )


def test_confirmation_requires_explicit_user_confirmation():
    with pytest.raises(ValueError, match="explicit user confirmation"):
        confirm_wardrobe_draft(
            _draft(),
            item_id="shirt-navy",
            confirmed_at_ms=1_700_000_000_100,
            confirmed_by_user=False,
        )


def test_confirmation_creates_available_confirmed_item_without_mutating_draft():
    draft = _draft()

    item = confirm_wardrobe_draft(
        draft,
        item_id="shirt-navy",
        confirmed_at_ms=1_700_000_000_100,
        confirmed_by_user=True,
    )

    assert draft.status == "pending"
    assert item.item_id == "shirt-navy"
    assert item.owner_person_id == draft.owner_person_id
    assert item.status == "confirmed"
    assert item.confirmed_by_user is True
    assert item.availability == "available"
    assert item.is_available is True
    assert item.source_evidence == draft.source_evidence


def test_non_available_confirmed_item_is_excluded_by_its_domain_state():
    item = ConfirmedWardrobeItem(
        item_id="shirt-navy",
        owner_person_id="primary-person",
        name="navy cotton shirt",
        category="top",
        source_evidence=[
            WardrobeSourceEvidence(source_type="manual", reference="closet shelf A")
        ],
        confirmed_at_ms=1_700_000_000_100,
        confirmed_by_user=True,
        availability="laundry",
    )

    assert item.is_available is False


def test_external_source_deduplication_requires_exact_type_and_reference_match():
    photo = _draft(
        source_type="photo",
        source_reference="  media://photo/2026-08-15-01  ",
    )
    same_photo = _draft(
        source_type="photo",
        source_reference="media://photo/2026-08-15-01",
    )
    link_with_same_reference = _draft(
        source_type="product_link",
        source_reference="media://photo/2026-08-15-01",
    )

    assert has_exact_external_source_duplicate(
        photo.source_evidence,
        same_photo.source_evidence,
    )
    assert not has_exact_external_source_duplicate(
        photo.source_evidence,
        link_with_same_reference.source_evidence,
    )


def test_manual_source_notes_are_not_deduplicated_even_when_identical():
    first = _draft(source_type="manual", source_reference="closet shelf A")
    second = _draft(source_type="manual", source_reference="closet shelf A")

    assert not has_exact_external_source_duplicate(
        first.source_evidence,
        second.source_evidence,
    )


def test_source_evidence_rejects_blank_reference():
    with pytest.raises(ValidationError, match="must not be blank"):
        WardrobeSourceEvidence(source_type="photo", reference="   ")
