# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Deterministic Outfit composition and explicit wear-confirmation service."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable

from miloco.life.outfit_feedback_event_repo import OutfitFeedbackEventRepo
from miloco.life.outfit_feedback_events import OutfitFeedbackEvent
from miloco.life.outfit_moment_service import OutfitMomentService
from miloco.life.outfit_recommendation_repo import OutfitRecommendationRepo
from miloco.life.outfit_recommendations import (
    ConfirmedOutfitWear,
    OutfitRecommendationOption,
    OutfitRecommendationResult,
    OutfitRecommendationSnapshot,
    OutfitScenarioInput,
)
from miloco.life.outfit_wardrobe import ConfirmedWardrobeItem
from miloco.life.outfit_wardrobe_service import OutfitWardrobeService


class OutfitRecommendationService:
    """Recommend only confirmed inventory and retain selection evidence."""

    def __init__(
        self,
        snapshots: OutfitRecommendationRepo,
        wardrobe: OutfitWardrobeService,
        events: OutfitFeedbackEventRepo,
        moments: OutfitMomentService,
        *,
        primary_person_id: str,
        clock_ms: Callable[[], int],
    ) -> None:
        self._snapshots = snapshots
        self._wardrobe = wardrobe
        self._events = events
        self._moments = moments
        self._primary_person_id = primary_person_id.strip()
        if not self._primary_person_id:
            raise ValueError("primary person id must not be blank")
        self._clock_ms = clock_ms

    def recommend(self, scenario: OutfitScenarioInput) -> OutfitRecommendationResult:
        """Create a stable snapshot only when enough context and inventory exist."""
        if not scenario.has_context():
            return OutfitRecommendationResult(
                status="needs_context",
                missing_context=("occasion_or_activity",),
            )

        options = _compose_options(self._wardrobe.list_confirmed_items())
        if not options:
            return OutfitRecommendationResult(
                status="insufficient_inventory",
                inventory_hints=_inventory_hints(self._wardrobe.list_confirmed_items()),
            )

        snapshot = self._snapshots.save_or_get(
            OutfitRecommendationSnapshot(
                recommendation_id=f"recommendation-{uuid.uuid4().hex}",
                owner_person_id=self._primary_person_id,
                scenario=scenario,
                options=options,
                created_at_ms=self._clock_ms(),
            )
        )
        return OutfitRecommendationResult(
            status="ready" if len(snapshot.options) >= 2 else "insufficient_inventory",
            recommendation_id=snapshot.recommendation_id,
            options=snapshot.options,
            inventory_hints=(
                () if len(snapshot.options) >= 2 else ("add_alternative_items",)
            ),
        )

    def confirm_recommended_wear(
        self,
        *,
        recommendation_id: str,
        option_id: str,
        confirmation_id: str,
        timezone: str,
        confirmed_by_user: bool,
    ) -> ConfirmedOutfitWear:
        """Append a user-confirmed fact only for an option in a stored snapshot."""
        if not confirmed_by_user:
            raise ValueError("explicit user confirmation is required")
        snapshot = self._snapshots.get_for_owner(
            self._primary_person_id,
            recommendation_id.strip(),
        )
        if snapshot is None:
            raise ValueError("Outfit recommendation not found")
        option = next(
            (
                candidate
                for candidate in snapshot.options
                if candidate.option_id == option_id.strip()
            ),
            None,
        )
        if option is None:
            raise ValueError("Outfit recommendation option not found")
        current_item_ids = {
            item.item_id for item in self._wardrobe.list_confirmed_items()
        }
        if not set(option.item_ids) <= current_item_ids:
            raise ValueError("recommended wardrobe items are no longer available")

        event_id = f"wear-{_require_confirmation_id(confirmation_id)}"
        existing = self._events.get_for_owner(event_id, self._primary_person_id)
        if existing is not None:
            _validate_replay(existing, snapshot, option)
            event = existing
        else:
            event = self._events.append(
                OutfitFeedbackEvent(
                    event_id=event_id,
                    owner_person_id=self._primary_person_id,
                    event_type="wear_confirmed",
                    recommendation_id=snapshot.recommendation_id,
                    item_ids=option.item_ids,
                    occurred_at_ms=self._clock_ms(),
                    confirmed_by_user=True,
                    evidence_refs=(
                        f"recommendation_snapshot:{snapshot.recommendation_id}",
                    ),
                )
            )
        moment = self._moments.project_confirmed_wear(
            event_id=event.event_id,
            owner_person_id=self._primary_person_id,
            timezone=timezone,
        )
        return ConfirmedOutfitWear(
            event_id=event.event_id,
            moment_id=moment.moment_id,
            recommendation_id=snapshot.recommendation_id,
            item_ids=option.item_ids,
            event=event,
            moment=moment,
        )


def _compose_options(
    items: list[ConfirmedWardrobeItem],
) -> tuple[OutfitRecommendationOption, ...]:
    by_category: defaultdict[str, list[ConfirmedWardrobeItem]] = defaultdict(list)
    for item in items:
        by_category[item.category].append(item)
    for category_items in by_category.values():
        category_items.sort(key=lambda item: (item.name.casefold(), item.item_id))

    options: list[OutfitRecommendationOption] = []
    for dress in by_category["dress"]:
        for shoes in by_category["shoes"]:
            options.append(
                OutfitRecommendationOption(
                    option_id=f"option-{len(options) + 1}",
                    item_ids=(dress.item_id, shoes.item_id),
                    composition_type="dress_shoes",
                )
            )
            if len(options) == 3:
                return tuple(options)
    for top in by_category["top"]:
        for bottom in by_category["bottom"]:
            for shoes in by_category["shoes"]:
                options.append(
                    OutfitRecommendationOption(
                        option_id=f"option-{len(options) + 1}",
                        item_ids=(top.item_id, bottom.item_id, shoes.item_id),
                        composition_type="top_bottom_shoes",
                    )
                )
                if len(options) == 3:
                    return tuple(options)
    return tuple(options)


def _inventory_hints(items: list[ConfirmedWardrobeItem]) -> tuple[str, ...]:
    categories = {item.category for item in items}
    hints: list[str] = []
    if "shoes" not in categories:
        hints.append("add_shoes")
    if "dress" not in categories and "top" not in categories:
        hints.append("add_top_or_dress")
    if "dress" not in categories and "bottom" not in categories:
        hints.append("add_bottom_or_dress")
    return tuple(hints or ["add_complete_outfit_items"])


def _require_confirmation_id(confirmation_id: str) -> str:
    confirmation_id = confirmation_id.strip()
    if not confirmation_id:
        raise ValueError("confirmation id must not be blank")
    return confirmation_id


def _validate_replay(
    event: OutfitFeedbackEvent,
    snapshot: OutfitRecommendationSnapshot,
    option: OutfitRecommendationOption,
) -> None:
    if (
        event.event_type != "wear_confirmed"
        or not event.confirmed_by_user
        or event.recommendation_id != snapshot.recommendation_id
        or event.item_ids != option.item_ids
    ):
        raise ValueError("wear confirmation replay conflicts with stored event")
