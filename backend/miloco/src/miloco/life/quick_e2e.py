# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""One-command vertical slice for outfit and cooking life-agent demo flows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from miloco.life.extractor import (
    LifeExtractionResult,
    extract_life_assets_from_mimo_mock,
)
from miloco.life.notify import LifeNotifyRequest, deliver_life_notification
from miloco.life.recommender import recommend_cooking, recommend_outfit
from miloco.life.repo import LifeRepo
from miloco.life.schema import CookingRecommendationRequest, OutfitRecommendationRequest


class QuickLifeE2EResult(BaseModel):
    source_id: str
    outfit_title: str
    outfit_broadcast_text: str
    cooking_title: str
    cooking_broadcast_text: str
    notify_channel: str
    notify_reason: str
    history_count: int
    history_domains: list[str]
    db_path: str
    report: str


def build_quick_life_e2e(
    fixture_path: str | Path,
    db_path: str | Path,
) -> QuickLifeE2EResult:
    """Run mock MiMo -> two recommendations -> notify fallback -> SQLite history."""
    fixture = Path(fixture_path)
    assets = _load_assets(fixture)
    outfit = recommend_outfit(
        OutfitRecommendationRequest(
            wardrobe_item_ids=[item.id for item in assets.wardrobe_items],
            person_id=_first_outfit_person_id(assets),
            occasion="tomorrow morning interview",
            weather="cool and cloudy",
            preference_tags=["not flashy"],
        ),
        wardrobe_items=assets.wardrobe_items,
        preferences=assets.preferences,
    )
    cooking = recommend_cooking(
        CookingRecommendationRequest(
            pantry_item_ids=[item.id for item in assets.pantry_items],
            people_count=3,
            time_budget_minutes=30,
            taste_tags=["light"],
            avoid_tags=["too salty"],
        ),
        pantry_items=assets.pantry_items,
        preferences=assets.preferences,
    )

    repo = LifeRepo(db_path)
    repo.save_extraction_result(assets)
    repo.record_recommendation("outfit", outfit, source_id=assets.source_id)
    repo.record_recommendation("cooking", cooking, source_id=assets.source_id)
    history = repo.list_recommendation_history(
        source_id=assets.source_id,
        limit=10,
    )
    notify = deliver_life_notification(
        LifeNotifyRequest(
            message=cooking.broadcast_text or cooking.options[0].summary,
            domain="cooking",
            urgency="medium",
            requires_ack=True,
        )
    )

    result = QuickLifeE2EResult(
        source_id=assets.source_id,
        outfit_title=outfit.options[0].title,
        outfit_broadcast_text=outfit.broadcast_text or "",
        cooking_title=cooking.options[0].title,
        cooking_broadcast_text=cooking.broadcast_text or "",
        notify_channel=notify.channel,
        notify_reason=notify.reason,
        history_count=len(history),
        history_domains=[row["domain"] for row in history],
        db_path=str(Path(db_path)),
        report="",
    )
    return result.model_copy(update={"report": _format_report(result)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="miloco-life-quick-e2e",
        description="Run the two-feature life-agent demo without live devices.",
    )
    parser.add_argument("fixture", help="Path to desensitized mock MiMo JSON.")
    parser.add_argument(
        "--db-path",
        default=".miloco-smoke/quick-life-e2e.db",
        help="SQLite path for the local quick E2E run.",
    )
    args = parser.parse_args(argv)

    result = build_quick_life_e2e(args.fixture, args.db_path)
    print(result.report)
    return 0


def _load_assets(fixture: Path) -> LifeExtractionResult:
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    return extract_life_assets_from_mimo_mock(payload)


def _first_outfit_person_id(assets: LifeExtractionResult) -> str | None:
    for preference in assets.preferences:
        if preference.domain == "outfit" and preference.person_id:
            return preference.person_id
    return None


def _format_report(result: QuickLifeE2EResult) -> str:
    return "\n".join(
        [
            "Miloco Life Agent Quick E2E",
            f"Source: {result.source_id}",
            f"Outfit flow: PASS - {result.outfit_title}",
            f"Outfit broadcast: {result.outfit_broadcast_text}",
            f"Cooking flow: PASS - {result.cooking_title}",
            f"Cooking broadcast: {result.cooking_broadcast_text}",
            f"Notify fallback: {result.notify_channel} ({result.notify_reason})",
            f"History count: {result.history_count}",
            f"History domains: {', '.join(result.history_domains)}",
            f"SQLite db: {result.db_path}",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
