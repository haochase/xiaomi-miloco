# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Contracts for the privacy-bounded Outfit wardrobe API DTOs."""

import pytest
from miloco.outfit.wardrobe import ConfirmedWardrobeItem, WardrobeItemDraft
from miloco.outfit.wardrobe_api import (
    ConfirmedWardrobeItemResponse,
    ConfirmWardrobeDraftRequest,
    CreateWardrobeDraftRequest,
    WardrobeApiProblem,
    WardrobeDraftResponse,
)
from pydantic import ValidationError


def test_create_draft_request_rejects_request_controlled_owner() -> None:
    with pytest.raises(ValidationError):
        CreateWardrobeDraftRequest.model_validate(
            {
                "name": "Navy shirt",
                "category": "top",
                "source_evidence": [
                    {"source_type": "manual", "reference": "closet shelf"}
                ],
                "owner_person_id": "another-person",
            }
        )


def test_confirm_draft_request_requires_explicit_true_confirmation() -> None:
    with pytest.raises(ValidationError):
        ConfirmWardrobeDraftRequest.model_validate({"confirmed_by_user": False})


def test_wardrobe_problem_allows_only_public_stable_codes() -> None:
    problem = WardrobeApiProblem(code="wardrobe_draft_not_found")

    assert problem.model_dump() == {"code": "wardrobe_draft_not_found"}
    with pytest.raises(ValidationError):
        WardrobeApiProblem.model_validate(
            {
                "code": "wardrobe_draft_not_found",
                "message": "E:\\private-media\\unsafe",
            }
        )


def test_draft_response_hides_owner_and_source_reference() -> None:
    draft = WardrobeItemDraft.model_validate(
        {
            "draft_id": "draft-1",
            "owner_person_id": "primary-person",
            "name": "Navy shirt",
            "category": "top",
            "source_evidence": [
                {
                    "source_type": "photo",
                    "reference": "E:\\private-media\\closet\\navy.jpg",
                }
            ],
            "created_at_ms": 100,
        }
    )

    response = WardrobeDraftResponse.from_domain(draft)

    assert response.model_dump() == {
        "draft_id": "draft-1",
        "name": "Navy shirt",
        "category": "top",
        "source_types": ("photo",),
        "status": "pending",
    }


def test_confirmed_response_exposes_available_state_without_owner_or_reference() -> (
    None
):
    item = ConfirmedWardrobeItem.model_validate(
        {
            "item_id": "item-draft-1",
            "owner_person_id": "primary-person",
            "name": "Navy shirt",
            "category": "top",
            "source_evidence": [
                {"source_type": "product_link", "reference": "https://shop.invalid/p/1"}
            ],
            "confirmed_at_ms": 200,
            "confirmed_by_user": True,
            "availability": "available",
        }
    )

    response = ConfirmedWardrobeItemResponse.from_domain(item)

    assert response.model_dump() == {
        "item_id": "item-draft-1",
        "name": "Navy shirt",
        "category": "top",
        "source_types": ("product_link",),
        "status": "confirmed",
        "availability": "available",
    }
