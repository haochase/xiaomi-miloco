# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Configured persistence composition for owner-bound Outfit moments."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from miloco.life.outfit_feedback_event_repo import OutfitFeedbackEventRepo
from miloco.life.outfit_installation import OutfitRuntimeContext
from miloco.life.outfit_media_repo import OutfitMediaRepo
from miloco.life.outfit_moment_repo import OutfitMomentRepo
from miloco.life.outfit_moment_service import OutfitMomentService
from miloco.life.outfit_moments import OutfitMoment
from miloco.life.outfit_recommendation_repo import OutfitRecommendationRepo
from miloco.life.outfit_recommendation_service import OutfitRecommendationService
from miloco.life.outfit_recommendations import (
    ConfirmedOutfitWear,
    OutfitRecommendationResult,
    OutfitScenarioInput,
)
from miloco.life.outfit_storage import OutfitStorage
from miloco.life.outfit_wardrobe_repo import OutfitWardrobeRepo
from miloco.life.outfit_wardrobe_service import OutfitWardrobeService


@dataclass(frozen=True)
class OutfitMomentRuntime:
    """Owner-bound services and configured private persistence paths."""

    primary_person_id: str
    database_path: Path
    feedback_event_db_path: Path
    moment_db_path: Path
    media_db_path: Path
    media_root: Path
    storage: OutfitStorage
    feedback_event_repo: OutfitFeedbackEventRepo
    moment_repo: OutfitMomentRepo
    media_repo: OutfitMediaRepo
    moment_service: OutfitMomentService
    wardrobe_service: OutfitWardrobeService
    recommendation_service: OutfitRecommendationService

    def project_confirmed_wear(self, *, event_id: str, timezone: str) -> OutfitMoment:
        """Project only the primary owner's previously confirmed wear fact."""
        return self.moment_service.project_confirmed_wear(
            event_id=event_id,
            owner_person_id=self.primary_person_id,
            timezone=timezone,
        )

    def recommend_outfit(
        self,
        scenario: OutfitScenarioInput,
    ) -> OutfitRecommendationResult:
        """Create an owner-bound inventory-only recommendation snapshot."""
        return self.recommendation_service.recommend(scenario)

    def confirm_recommended_wear(
        self,
        *,
        recommendation_id: str,
        option_id: str,
        confirmation_id: str,
        timezone: str,
        confirmed_by_user: bool,
    ) -> ConfirmedOutfitWear:
        """Persist a user-confirmed option and project its historical moment."""
        return self.recommendation_service.confirm_recommended_wear(
            recommendation_id=recommendation_id,
            option_id=option_id,
            confirmation_id=confirmation_id,
            timezone=timezone,
            confirmed_by_user=confirmed_by_user,
        )


def build_outfit_moment_runtime(
    context: OutfitRuntimeContext,
    *,
    clock_ms: Callable[[], int],
) -> OutfitMomentRuntime:
    """Construct moment persistence solely from the installed host context."""
    primary_person_id = _require_primary_person_id(context)
    storage_dir = _resolve_storage_dir(context)
    database_path = storage_dir / "outfit.db"
    media_root = storage_dir / "media"
    storage = OutfitStorage(database_path)
    feedback_event_repo = OutfitFeedbackEventRepo(storage)
    moment_repo = OutfitMomentRepo(storage)
    media_repo = OutfitMediaRepo(storage, media_root)
    wardrobe_service = OutfitWardrobeService(
        OutfitWardrobeRepo(storage),
        primary_person_id=primary_person_id,
        clock_ms=clock_ms,
    )

    moment_service = OutfitMomentService(
        feedback_event_repo,
        moment_repo,
        clock_ms=clock_ms,
    )
    return OutfitMomentRuntime(
        primary_person_id=primary_person_id,
        database_path=database_path,
        feedback_event_db_path=database_path,
        moment_db_path=database_path,
        media_db_path=database_path,
        media_root=media_root,
        storage=storage,
        feedback_event_repo=feedback_event_repo,
        moment_repo=moment_repo,
        media_repo=media_repo,
        moment_service=moment_service,
        wardrobe_service=wardrobe_service,
        recommendation_service=OutfitRecommendationService(
            OutfitRecommendationRepo(storage),
            wardrobe_service,
            feedback_event_repo,
            moment_service,
            primary_person_id=primary_person_id,
            clock_ms=clock_ms,
        ),
    )


def _resolve_storage_dir(context: OutfitRuntimeContext) -> Path:
    workspace_dir = context.workspace_dir.resolve()
    storage_dir = context.storage_dir.resolve()
    if workspace_dir not in storage_dir.parents:
        raise ValueError("Outfit storage must stay inside the configured workspace")
    return storage_dir


def _require_primary_person_id(context: OutfitRuntimeContext) -> str:
    primary_person_id = context.primary_person_id.strip()
    if not primary_person_id:
        raise ValueError("Outfit primary person id must not be blank")
    return primary_person_id
