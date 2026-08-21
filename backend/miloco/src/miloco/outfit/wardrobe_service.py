# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Primary-user application service for the Outfit wardrobe lifecycle."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from miloco.outfit.wardrobe import (
    ConfirmedWardrobeItem,
    WardrobeCategory,
    WardrobeItemDraft,
    WardrobeSourceEvidence,
    confirm_wardrobe_draft,
)
from miloco.outfit.wardrobe_repo import WardrobeRepository


class WardrobeService:
    """Keep primary-owner injection outside requests and repository callers."""

    def __init__(
        self,
        repository: WardrobeRepository,
        *,
        primary_person_id: str,
        clock_ms: Callable[[], int],
        draft_id_factory: Callable[[], str] | None = None,
    ) -> None:
        normalized_primary_person_id = primary_person_id.strip()
        if not normalized_primary_person_id:
            raise ValueError("primary_person_id must not be blank")

        self._repository = repository
        self._primary_person_id = normalized_primary_person_id
        self._clock_ms = clock_ms
        self._draft_id_factory = draft_id_factory or _new_draft_id

    @property
    def primary_person_id(self) -> str:
        """Return the construction-injected inventory owner."""

        return self._primary_person_id

    def create_draft(
        self,
        *,
        name: str,
        category: WardrobeCategory,
        source_evidence: tuple[WardrobeSourceEvidence, ...],
    ) -> WardrobeItemDraft:
        """Create a pending review fact owned only by the configured user."""

        draft = WardrobeItemDraft(
            draft_id=self._draft_id_factory(),
            owner_person_id=self._primary_person_id,
            name=name,
            category=category,
            source_evidence=source_evidence,
            created_at_ms=self._clock_ms(),
        )
        self._repository.add_pending_draft(draft)
        return draft

    def confirm_draft(
        self,
        draft_id: str,
        *,
        confirmed_by_user: bool,
    ) -> ConfirmedWardrobeItem:
        """Promote an owner-scoped draft only after explicit confirmation."""

        if confirmed_by_user is not True:
            raise ValueError("explicit user confirmation is required")

        item_id = f"item-{draft_id}"
        draft = self._repository.get_draft_for_owner(
            self._primary_person_id,
            draft_id,
        )
        if draft is None:
            existing_item = self._repository.get_confirmed_item_for_owner(
                self._primary_person_id,
                item_id,
            )
            if existing_item is not None:
                return existing_item
            raise ValueError("wardrobe draft not found")
        if draft.status != "pending":
            raise ValueError("wardrobe draft is no longer pending")

        item = confirm_wardrobe_draft(
            draft,
            item_id=item_id,
            confirmed_at_ms=self._clock_ms(),
            confirmed_by_user=confirmed_by_user,
        )
        return self._repository.confirm_pending_draft(
            draft_id=draft.draft_id,
            item=item,
        )

    def list_pending_drafts(self) -> tuple[WardrobeItemDraft, ...]:
        """Return only this host-configured primary user's pending drafts."""

        return self._repository.list_pending_drafts(self._primary_person_id)

    def list_confirmed_available_items(self) -> tuple[ConfirmedWardrobeItem, ...]:
        """Return recommendation-eligible inventory for the configured owner."""

        return self._repository.list_confirmed_available_items(self._primary_person_id)


def _new_draft_id() -> str:
    return f"draft-{uuid.uuid4().hex}"
