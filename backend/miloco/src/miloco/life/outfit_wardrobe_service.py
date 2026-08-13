# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Application service for configured primary-user wardrobe lifecycle."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from miloco.life.outfit_wardrobe import (
    ConfirmedWardrobeItem,
    WardrobeCategory,
    WardrobeDraftInput,
    WardrobeItemDraft,
    requires_exact_source_deduplication,
)
from miloco.life.outfit_wardrobe_repo import OutfitWardrobeRepo


class OutfitWardrobeService:
    """Create pending drafts and confirm only facts owned by the configured user."""

    def __init__(
        self,
        repo: OutfitWardrobeRepo,
        *,
        primary_person_id: str,
        clock_ms: Callable[[], int],
    ) -> None:
        self._repo = repo
        self._primary_person_id = primary_person_id.strip()
        if not self._primary_person_id:
            raise ValueError("primary person id must not be blank")
        self._clock_ms = clock_ms

    def create_draft(self, input: WardrobeDraftInput) -> WardrobeItemDraft:
        draft = WardrobeItemDraft(
            draft_id=f"draft-{uuid.uuid4().hex}",
            owner_person_id=self._primary_person_id,
            name=input.name,
            category=input.category,
            source_type=input.source_type,
            source_reference=input.source_reference,
            created_at_ms=self._clock_ms(),
        )
        return self._repo.save_draft_or_get(draft)

    def confirm_draft(
        self, draft_id: str, *, confirmed_by_user: bool
    ) -> ConfirmedWardrobeItem:
        if not confirmed_by_user:
            raise ValueError("explicit user confirmation is required")
        draft = self._repo.get_draft_for_owner(self._primary_person_id, draft_id)
        if draft is None:
            raise ValueError("wardrobe draft not found")
        item_id = f"item-{draft.draft_id}"
        existing_item = self._repo.get_item_for_owner(self._primary_person_id, item_id)
        if existing_item is not None:
            return existing_item
        if draft.status != "pending":
            raise ValueError("wardrobe draft is no longer pending")
        if requires_exact_source_deduplication(
            draft.source_type
        ) and self._repo.has_exact_source(
            self._primary_person_id,
            source_type=draft.source_type,
            source_reference=draft.source_reference,
        ):
            raise ValueError("duplicate wardrobe source already confirmed")
        item = self._repo.save_item_or_get(
            ConfirmedWardrobeItem(
                item_id=item_id,
                owner_person_id=self._primary_person_id,
                name=draft.name,
                category=draft.category,
                source_type=draft.source_type,
                source_reference=draft.source_reference,
                confirmed_at_ms=self._clock_ms(),
            )
        )
        self._repo.update_draft(draft.model_copy(update={"status": "confirmed"}))
        return item

    def list_pending_drafts(self) -> list[WardrobeItemDraft]:
        return self._repo.list_drafts_for_owner(
            self._primary_person_id,
            status="pending",
        )

    def discard_draft(self, draft_id: str, *, confirmed_by_user: bool) -> None:
        if not confirmed_by_user:
            raise ValueError("explicit user confirmation is required")
        draft = self._repo.get_draft_for_owner(self._primary_person_id, draft_id)
        if draft is None:
            raise ValueError("wardrobe draft not found")
        if draft.status != "pending":
            raise ValueError("wardrobe draft is no longer pending")
        self._repo.update_draft(draft.model_copy(update={"status": "discarded"}))

    def update_item(
        self,
        item_id: str,
        *,
        name: str | None,
        category: WardrobeCategory | None,
    ) -> ConfirmedWardrobeItem:
        if name is None and category is None:
            raise ValueError("at least one wardrobe field must be updated")
        item = self._repo.get_item_for_owner(self._primary_person_id, item_id)
        if item is None:
            raise ValueError("wardrobe item not found")
        updated = ConfirmedWardrobeItem.model_validate(
            {
                **item.model_dump(),
                **({"name": name} if name is not None else {}),
                **({"category": category} if category is not None else {}),
            }
        )
        return self._repo.update_item(updated)

    def delete_item(self, item_id: str, *, confirmed_by_user: bool) -> None:
        if not confirmed_by_user:
            raise ValueError("explicit user confirmation is required")
        if not self._repo.delete_item_for_owner(self._primary_person_id, item_id):
            raise ValueError("wardrobe item not found")

    def list_confirmed_items(self) -> list[ConfirmedWardrobeItem]:
        return self._repo.list_items_for_owner(self._primary_person_id)
