# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Projection service from confirmed Outfit feedback facts to moments."""

from __future__ import annotations

from collections.abc import Callable

from miloco.life.outfit_feedback_event_repo import OutfitFeedbackEventRepo
from miloco.life.outfit_moment_repo import OutfitMomentRepo
from miloco.life.outfit_moment_signals import (
    build_candidate_tags,
    derive_moment_signals,
)
from miloco.life.outfit_moments import OutfitMoment, OutfitMomentTag


class OutfitMomentService:
    """Create and read owner-scoped moment projections from stored facts."""

    def __init__(
        self,
        events: OutfitFeedbackEventRepo,
        moments: OutfitMomentRepo,
        *,
        clock_ms: Callable[[], int],
    ):
        self._events = events
        self._moments = moments
        self._clock_ms = clock_ms

    def project_confirmed_wear(
        self, *, event_id: str, owner_person_id: str, timezone: str
    ) -> OutfitMoment:
        event = self._events.get_for_owner(event_id, owner_person_id)
        if event is None:
            raise ValueError("confirmed wear event not found")
        if event.event_type != "wear_confirmed" or not event.confirmed_by_user:
            raise ValueError("event is not an explicitly confirmed wear")
        moment = OutfitMoment(
            moment_id=f"moment-{event.event_id}",
            owner_person_id=event.owner_person_id,
            occurred_at_ms=event.occurred_at_ms,
            timezone=timezone,
            recommendation_id=event.recommendation_id,
            confirmed_wear_event_id=event.event_id,
            item_ids=event.item_ids,
            source_event_ids=(event.event_id,),
            created_at_ms=self._clock_ms(),
        )
        return self._moments.save_or_get(moment)

    def get_for_owner(
        self, *, owner_person_id: str, moment_id: str
    ) -> OutfitMoment | None:
        return self._moments.get_for_owner(owner_person_id, moment_id)

    def list_for_owner(
        self, *, owner_person_id: str, limit: int, since_ms: int | None
    ) -> list[OutfitMoment]:
        return self._moments.list_for_owner(
            owner_person_id, limit=limit, since_ms=since_ms
        )

    def refresh_tags(
        self, moment_id: str, *, owner_person_id: str
    ) -> list[OutfitMomentTag]:
        moment = self.get_for_owner(
            owner_person_id=owner_person_id, moment_id=moment_id
        )
        if moment is None:
            raise ValueError("Outfit moment not found")
        history = self._moments.list_for_owner(owner_person_id, limit=1000)
        candidates = build_candidate_tags(
            derive_moment_signals(moment, history=history)
        )
        return self._moments.store_candidate_tags(
            owner_person_id, moment_id, candidates
        )

    def list_tags(
        self, moment_id: str, *, owner_person_id: str
    ) -> list[OutfitMomentTag]:
        return self._moments.list_tags_for_owner(owner_person_id, moment_id)

    def confirm_tag(self, tag_id: str, *, owner_person_id: str) -> OutfitMomentTag:
        return self._review_tag(
            tag_id, owner_person_id=owner_person_id, review_status="confirmed"
        )

    def reject_tag(self, tag_id: str, *, owner_person_id: str) -> OutfitMomentTag:
        return self._review_tag(
            tag_id, owner_person_id=owner_person_id, review_status="rejected"
        )

    def edit_tag(
        self,
        tag_id: str,
        *,
        owner_person_id: str,
        label: str | None,
        narrative: str | None,
    ) -> OutfitMomentTag:
        if label is None and narrative is None:
            raise ValueError("tag edit requires label or narrative")
        updated = self._moments.update_tag_for_owner(
            owner_person_id,
            tag_id,
            review_status="edited",
            label=label,
            narrative=narrative,
        )
        if updated is None:
            raise ValueError("Outfit tag not found")
        return updated

    def _review_tag(
        self, tag_id: str, *, owner_person_id: str, review_status: str
    ) -> OutfitMomentTag:
        updated = self._moments.update_tag_for_owner(
            owner_person_id, tag_id, review_status=review_status
        )
        if updated is None:
            raise ValueError("Outfit tag not found")
        return updated
