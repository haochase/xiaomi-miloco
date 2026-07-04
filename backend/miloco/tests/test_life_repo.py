# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""SQLite persistence tests for the life-domain demo assets."""

from __future__ import annotations

import json
from pathlib import Path

from miloco.life.extractor import extract_life_assets_from_mimo_mock
from miloco.life.recommender import recommend_cooking, recommend_outfit
from miloco.life.schema import CookingRecommendationRequest, OutfitRecommendationRequest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "life_mimo_mock.json"


def _demo_assets():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return extract_life_assets_from_mimo_mock(payload)


def test_repo_saves_mock_mimo_assets_for_reviewable_inventory(tmp_path):
    from miloco.life.repo import LifeRepo

    repo = LifeRepo(tmp_path / "life.db")
    assets = _demo_assets()

    summary = repo.save_extraction_result(assets)

    assert summary == {
        "source_id": "demo_afternoon_interview_dinner",
        "wardrobe_count": 2,
        "pantry_count": 3,
        "preference_count": 2,
    }
    wardrobe = repo.list_wardrobe_items()
    pantry = repo.list_pantry_items()
    assert [item.id for item in wardrobe[:2]] == ["blazer_gray", "shirt_white"]
    assert wardrobe[0].source_type == "mimo_mock"
    assert [item.id for item in pantry[:2]] == ["egg_1", "tomato_1"]
    assert pantry[0].storage == "fridge"


def test_repo_records_recommendation_history_with_safe_broadcast_text(tmp_path):
    from miloco.life.repo import LifeRepo

    repo = LifeRepo(tmp_path / "life.db")
    assets = _demo_assets()
    repo.save_extraction_result(assets)

    outfit = recommend_outfit(
        OutfitRecommendationRequest(
            wardrobe_item_ids=["blazer_gray", "shirt_white"],
            occasion="tomorrow morning interview",
            weather="cool and cloudy",
            preference_tags=["not flashy"],
        ),
        wardrobe_items=assets.wardrobe_items,
        preferences=assets.preferences,
    )
    cooking = recommend_cooking(
        CookingRecommendationRequest(
            pantry_item_ids=["egg_1", "tomato_1", "dumpling_1"],
            people_count=3,
            time_budget_minutes=30,
            taste_tags=["light"],
        ),
        pantry_items=assets.pantry_items,
        preferences=assets.preferences,
    )

    outfit_id = repo.record_recommendation("outfit", outfit, source_id=assets.source_id)
    cooking_id = repo.record_recommendation(
        "cooking", cooking, source_id=assets.source_id
    )

    history = repo.list_recommendation_history()
    assert [row["id"] for row in history] == [cooking_id, outfit_id]
    assert history[0]["domain"] == "cooking"
    assert "请先确认锅具状态和食材新鲜度" in history[0]["broadcast_text"]
    assert history[0]["option_titles"] == ["番茄鸡蛋配速冻饺子"]


def test_repo_lists_readable_recommendation_history_with_domain_and_limit(tmp_path):
    from miloco.life.repo import LifeRepo

    repo = LifeRepo(tmp_path / "life.db")
    assets = _demo_assets()
    repo.save_extraction_result(assets)
    outfit = recommend_outfit(
        OutfitRecommendationRequest(
            wardrobe_item_ids=["blazer_gray", "shirt_white"],
            occasion="tomorrow morning interview",
        ),
        wardrobe_items=assets.wardrobe_items,
        preferences=assets.preferences,
    )
    cooking = recommend_cooking(
        CookingRecommendationRequest(
            pantry_item_ids=["egg_1", "tomato_1", "dumpling_1"],
            people_count=3,
            time_budget_minutes=30,
        ),
        pantry_items=assets.pantry_items,
        preferences=assets.preferences,
    )
    repo.record_recommendation("outfit", outfit, source_id=assets.source_id)
    repo.record_recommendation("cooking", cooking, source_id=assets.source_id)

    history = repo.list_recommendation_history(domain="cooking", limit=1)

    assert len(history) == 1
    assert history[0]["domain"] == "cooking"
    assert history[0]["source_id"] == "demo_afternoon_interview_dinner"
    assert history[0]["option_titles"] == ["番茄鸡蛋配速冻饺子"]
    assert history[0]["broadcast_text"] == cooking.broadcast_text
    assert history[0]["created_at"]


def test_repo_lists_recommendation_history_for_one_source_id(tmp_path):
    from miloco.life.repo import LifeRepo

    repo = LifeRepo(tmp_path / "life.db")
    assets = _demo_assets()
    repo.save_extraction_result(assets)
    outfit = recommend_outfit(
        OutfitRecommendationRequest(
            wardrobe_item_ids=["blazer_gray", "shirt_white"],
            occasion="tomorrow morning interview",
        ),
        wardrobe_items=assets.wardrobe_items,
        preferences=assets.preferences,
    )
    cooking = recommend_cooking(
        CookingRecommendationRequest(
            pantry_item_ids=["egg_1", "tomato_1", "dumpling_1"],
            people_count=3,
            time_budget_minutes=30,
        ),
        pantry_items=assets.pantry_items,
        preferences=assets.preferences,
    )
    repo.record_recommendation("outfit", outfit, source_id=assets.source_id)
    repo.record_recommendation("cooking", cooking, source_id="older_demo_source")

    history = repo.list_recommendation_history(
        source_id="demo_afternoon_interview_dinner"
    )

    assert len(history) == 1
    assert history[0]["domain"] == "outfit"
    assert history[0]["source_id"] == "demo_afternoon_interview_dinner"


def test_repo_summarizes_empty_history_with_recording_hint(tmp_path):
    from miloco.life.repo import LifeRepo

    repo = LifeRepo(tmp_path / "life.db")

    summary = repo.summarize_recommendation_history(domain="cooking")

    assert summary == {
        "count": 0,
        "history": [],
        "history_hint": (
            "No cooking recommendation history yet. Run the life demo with "
            "--persist before recording the history step."
        ),
    }
