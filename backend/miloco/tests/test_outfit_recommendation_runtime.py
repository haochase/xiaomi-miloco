# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Deterministic primary-user Outfit recommendation and wear contracts."""

from pathlib import Path

import pytest
from miloco.life.outfit_installation import OutfitRuntimeContext
from miloco.life.outfit_moment_runtime import build_outfit_moment_runtime
from miloco.life.outfit_recommendations import OutfitScenarioInput
from miloco.life.outfit_wardrobe import WardrobeDraftInput


def _runtime(tmp_path: Path):
    workspace_dir = tmp_path / "miloco-home"
    workspace_dir.mkdir()
    return build_outfit_moment_runtime(
        OutfitRuntimeContext(
            primary_person_id="primary-person",
            workspace_dir=workspace_dir,
            storage_dir=workspace_dir / "outfit",
        ),
        clock_ms=lambda: 2_000,
    )


def _confirm_item(runtime, *, name: str, category: str) -> str:
    draft = runtime.wardrobe_service.create_draft(
        WardrobeDraftInput(
            name=name,
            category=category,
            source_type="manual",
            source_reference=f"closet:{name}",
        )
    )
    return runtime.wardrobe_service.confirm_draft(
        draft.draft_id,
        confirmed_by_user=True,
    ).item_id


def test_recommendation_uses_only_confirmed_primary_user_inventory(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    navy_top = _confirm_item(runtime, name="navy cotton shirt", category="top")
    white_top = _confirm_item(runtime, name="white linen shirt", category="top")
    trousers = _confirm_item(runtime, name="charcoal trousers", category="bottom")
    shoes = _confirm_item(runtime, name="black loafers", category="shoes")

    recommendation = runtime.recommend_outfit(
        OutfitScenarioInput(occasion="team meeting")
    )

    assert recommendation.status == "ready"
    assert recommendation.recommendation_id is not None
    assert len(recommendation.options) == 2
    assert [option.item_ids for option in recommendation.options] == [
        (navy_top, trousers, shoes),
        (white_top, trousers, shoes),
    ]
    assert all(
        item_id in {navy_top, white_top, trousers, shoes}
        for option in recommendation.options
        for item_id in option.item_ids
    )


def test_recommendation_asks_for_scenario_instead_of_guessing(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    recommendation = runtime.recommend_outfit(OutfitScenarioInput())

    assert recommendation.status == "needs_context"
    assert recommendation.recommendation_id is None
    assert recommendation.missing_context == ("occasion_or_activity",)
    assert recommendation.options == ()


def test_weather_or_day_kind_only_does_not_replace_a_user_scenario(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)

    recommendation = runtime.recommend_outfit(
        OutfitScenarioInput(day_kind="workday", weather_summary="rainy")
    )

    assert recommendation.status == "needs_context"
    assert recommendation.missing_context == ("occasion_or_activity",)


def test_incomplete_inventory_returns_only_hints_not_a_fake_recommendation(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    _confirm_item(runtime, name="navy cotton shirt", category="top")

    recommendation = runtime.recommend_outfit(
        OutfitScenarioInput(occasion="team meeting")
    )

    assert recommendation.status == "insufficient_inventory"
    assert recommendation.recommendation_id is None
    assert recommendation.options == ()
    assert set(recommendation.inventory_hints) == {"add_bottom_or_dress", "add_shoes"}


def test_confirmed_recommendation_option_creates_replay_safe_wear_fact_and_moment(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    _confirm_item(runtime, name="navy cotton shirt", category="top")
    _confirm_item(runtime, name="white linen shirt", category="top")
    _confirm_item(runtime, name="charcoal trousers", category="bottom")
    _confirm_item(runtime, name="black loafers", category="shoes")
    recommendation = runtime.recommend_outfit(
        OutfitScenarioInput(occasion="team meeting")
    )

    first = runtime.confirm_recommended_wear(
        recommendation_id=recommendation.recommendation_id or "",
        option_id=recommendation.options[0].option_id,
        confirmation_id="meeting-wear-20260812",
        timezone="Asia/Shanghai",
        confirmed_by_user=True,
    )
    replayed = runtime.confirm_recommended_wear(
        recommendation_id=recommendation.recommendation_id or "",
        option_id=recommendation.options[0].option_id,
        confirmation_id="meeting-wear-20260812",
        timezone="Asia/Shanghai",
        confirmed_by_user=True,
    )

    assert first == replayed
    assert first.event.event_type == "wear_confirmed"
    assert first.event.confirmed_by_user is True
    assert first.event.evidence_refs == (
        f"recommendation_snapshot:{recommendation.recommendation_id}",
    )
    assert first.moment.recommendation_id == recommendation.recommendation_id
    assert first.moment.item_ids == recommendation.options[0].item_ids


def test_wear_confirmation_rejects_an_option_outside_the_stored_snapshot(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    _confirm_item(runtime, name="navy cotton shirt", category="top")
    _confirm_item(runtime, name="charcoal trousers", category="bottom")
    _confirm_item(runtime, name="black loafers", category="shoes")
    recommendation = runtime.recommend_outfit(
        OutfitScenarioInput(occasion="team meeting")
    )

    with pytest.raises(ValueError, match="option not found"):
        runtime.confirm_recommended_wear(
            recommendation_id=recommendation.recommendation_id or "",
            option_id="option-injected-by-client",
            confirmation_id="tampered-option",
            timezone="Asia/Shanghai",
            confirmed_by_user=True,
        )
