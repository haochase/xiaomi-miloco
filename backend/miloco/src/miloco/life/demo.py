# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Command-line demo runner for the life-domain hackathon loop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from miloco.life.extractor import (
    LifeExtractionResult,
    extract_life_assets_from_mimo_mock,
)
from miloco.life.recommender import recommend_cooking, recommend_outfit
from miloco.life.schema import CookingRecommendationRequest, OutfitRecommendationRequest


def build_life_demo_report(fixture_path: str | Path) -> str:
    """Run fixture -> mock MiMo extractor -> recommender and format demo output."""
    fixture = Path(fixture_path)
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    assets = extract_life_assets_from_mimo_mock(payload)

    outfit = recommend_outfit(
        OutfitRecommendationRequest(
            wardrobe_item_ids=[item.id for item in assets.wardrobe_items],
            person_id=_first_person_id(assets),
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

    return "\n".join(
        [
            "Miloco Life Agent Demo",
            f"Mock MiMo source: {assets.source_id}",
            f"Caption: {assets.caption or 'n/a'}",
            "",
            _format_option("Outfit", outfit.options[0], outfit.broadcast_text),
            "",
            _format_option("Cooking", cooking.options[0], cooking.broadcast_text),
            "",
            _format_low_confidence_notes(assets),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="miloco-life-demo",
        description="Run the hackathon life-agent fixture through mock MiMo extraction and recommendations.",
    )
    parser.add_argument(
        "fixture", help="Path to a desensitized mock MiMo JSON fixture."
    )
    args = parser.parse_args(argv)

    print(build_life_demo_report(args.fixture))
    return 0


def _first_person_id(assets: LifeExtractionResult) -> str | None:
    for preference in assets.preferences:
        if preference.domain == "outfit" and preference.person_id:
            return preference.person_id
    return None


def _format_option(label: str, option, broadcast_text: str | None) -> str:
    lines = [
        f"{label}: {option.title}",
        f"Summary: {option.summary}",
        "Rationale:",
        *[f"- {item}" for item in option.rationale],
    ]
    if option.safety_notes:
        lines.extend(["Safety notes:", *[f"- {item}" for item in option.safety_notes]])
    if broadcast_text:
        lines.append(f"Broadcast: {broadcast_text}")
    return "\n".join(lines)


def _format_low_confidence_notes(assets: LifeExtractionResult) -> str:
    if not assets.low_confidence_notes:
        return "Low confidence notes: none"
    lines = ["Low confidence notes:"]
    lines.extend(f"- {note}" for note in assets.low_confidence_notes)
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
