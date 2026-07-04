# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Service orchestration for life-agent demo flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from miloco.life.extractor import (
    LifeExtractionResult,
    extract_life_assets_from_mimo_mock,
)
from miloco.life.intent import (
    COOKING_INITIAL_TERMS,
    OUTFIT_INITIAL_TERMS,
    VISUAL_REFERENCE_TERMS,
    infer_life_occasion,
    infer_life_weather,
)
from miloco.life.mimo_live import (
    extract_life_assets_with_live_mimo,
    normalize_live_mimo_life_payload,
)
from miloco.life.recommender import recommend_cooking, recommend_outfit
from miloco.life.repo import LifeRepo
from miloco.life.resource_lease import ResourceLeaseManager
from miloco.life.schema import (
    CookingRecommendationRequest,
    LifeDomain,
    LifePreference,
    OutfitRecommendationRequest,
    RecommendationOption,
    RecommendationResult,
)
from miloco.life.visual_input import VisualObservation, observation_from_live_request

LifeTriggerSource = Literal["manual", "voice_intent", "schedule", "device_state"]
LIFE_TRIGGER_SOURCES = {"manual", "voice_intent", "schedule", "device_state"}
DEFAULT_LIFE_TRIGGER_PROMPT = (
    "Extract only the assets needed for this explicit life-agent request."
)
_MIMO_LEASE_MANAGER = ResourceLeaseManager()
_MIMO_BUSY_MESSAGE = "视觉理解正在处理上一条请求，请稍后再试。"


class LifeDemoPayload(Protocol):
    mimo_payload: dict[str, Any] | str
    occasion: str
    weather: str | None
    people_count: int
    time_budget_minutes: int
    persist: bool
    db_path: str | None


class LifeLiveDemoPayload(Protocol):
    source_id: str
    prompt: str
    clip_base64: str | None
    mimo_payload: dict[str, Any] | str | None
    occasion: str
    weather: str | None
    people_count: int
    time_budget_minutes: int
    persist: bool
    db_path: str | None


class LifeTriggerPayload(Protocol):
    trigger_source: LifeTriggerSource
    domain: LifeDomain
    source_id: str | None
    prompt: str | None
    clip_base64: str | None
    mimo_payload: dict[str, Any] | str | None
    occasion: str
    weather: str | None
    people_count: int
    time_budget_minutes: int
    persist: bool
    db_path: str | None


class LifeTextTriggerPayload(Protocol):
    text: str
    trigger_source: LifeTriggerSource
    source_id: str | None
    prompt: str | None
    clip_base64: str | None
    mimo_payload: dict[str, Any] | str | None
    occasion: str
    weather: str | None
    people_count: int
    time_budget_minutes: int
    persist: bool
    db_path: str | None


@dataclass(frozen=True)
class _LifeTextIntent:
    domain: LifeDomain
    requires_visual_input: bool
    prompt: str
    matched_terms: list[str]


@dataclass(frozen=True)
class _LifeTriggerAdapter:
    trigger_source: LifeTriggerSource
    domain: LifeDomain
    source_id: str | None
    prompt: str | None
    clip_base64: str | None
    mimo_payload: dict[str, Any] | str | None
    occasion: str
    weather: str | None
    people_count: int
    time_budget_minutes: int
    persist: bool
    db_path: str | None


def run_life_demo(payload: LifeDemoPayload) -> dict[str, Any]:
    """Run the mock/demo life-agent flow and return API-ready data."""
    assets = extract_life_assets_from_mimo_mock(payload.mimo_payload)
    outfit = recommend_outfit(
        OutfitRecommendationRequest(
            wardrobe_item_ids=[item.id for item in assets.wardrobe_items],
            person_id=_first_outfit_person_id(assets.preferences),
            occasion=payload.occasion,
            weather=payload.weather,
            preference_tags=["not flashy"],
        ),
        wardrobe_items=assets.wardrobe_items,
        preferences=assets.preferences,
    )
    cooking = recommend_cooking(
        CookingRecommendationRequest(
            pantry_item_ids=[item.id for item in assets.pantry_items],
            people_count=payload.people_count,
            time_budget_minutes=payload.time_budget_minutes,
            taste_tags=["light"],
            avoid_tags=["too salty"],
        ),
        pantry_items=assets.pantry_items,
        preferences=assets.preferences,
    )

    data = {
        "source_id": assets.source_id,
        "caption": assets.caption,
        "outfit": _option_payload(outfit.options[0]),
        "outfit_broadcast_text": outfit.broadcast_text,
        "cooking": _option_payload(cooking.options[0]),
        "cooking_broadcast_text": cooking.broadcast_text,
        "low_confidence_notes": assets.low_confidence_notes,
    }
    if payload.persist:
        data["persistence"] = _persist_results(
            payload.db_path,
            assets,
            outfit=outfit,
            cooking=cooking,
        )
    return data


async def run_life_live_demo(payload: LifeLiveDemoPayload) -> dict[str, Any]:
    """Run the live life-agent flow from either MiMo payload or visual input."""
    observation = observation_from_live_request(
        source_id=payload.source_id,
        prompt=payload.prompt,
        clip_base64=payload.clip_base64,
        mimo_payload=payload.mimo_payload,
    )
    if observation.mimo_payload is not None:
        assets = normalize_live_mimo_life_payload(
            observation.mimo_payload,
            fallback_source_id=observation.source_id,
        )
        mimo_source = "provided_payload"
    else:
        assets, _raw_mimo_text, mimo_lease = await _extract_life_assets_with_mimo_lease(
            observation,
        )
        mimo_source = "live_mimo"
        if assets is None:
            return _live_mimo_busy_data(observation, mimo_lease)

    outfit = _recommend_outfit_if_possible(payload, assets)
    cooking = _recommend_cooking_if_possible(payload, assets)
    data = {
        "source_id": assets.source_id,
        "mimo_source": mimo_source,
        "caption": assets.caption,
        "visual_source_type": observation.source_type,
        "outfit": _option_payload(outfit.options[0]) if outfit else None,
        "outfit_broadcast_text": outfit.broadcast_text if outfit else None,
        "cooking": _option_payload(cooking.options[0]) if cooking else None,
        "cooking_broadcast_text": cooking.broadcast_text if cooking else None,
        "low_confidence_notes": assets.low_confidence_notes,
    }
    if payload.persist:
        data["persistence"] = _persist_results(
            payload.db_path,
            assets,
            outfit=outfit,
            cooking=cooking,
        )
    return data


async def run_life_trigger(payload: LifeTriggerPayload) -> dict[str, Any]:
    """Run one life-agent recommendation from an explicit on-demand trigger."""
    source_id = payload.source_id or f"{payload.trigger_source}:{payload.domain}"
    repo = LifeRepo(payload.db_path or "data/life-demo.db")
    used_visual_input = bool(payload.clip_base64 or payload.mimo_payload)

    if used_visual_input:
        observation = observation_from_live_request(
            source_id=source_id,
            prompt=payload.prompt or DEFAULT_LIFE_TRIGGER_PROMPT,
            clip_base64=payload.clip_base64,
            mimo_payload=payload.mimo_payload,
        )
        if observation.mimo_payload is not None:
            assets = normalize_live_mimo_life_payload(
                observation.mimo_payload,
                fallback_source_id=observation.source_id,
            )
        else:
            (
                assets,
                _raw_mimo_text,
                mimo_lease,
            ) = await _extract_life_assets_with_mimo_lease(observation)
            if assets is None:
                return _trigger_mimo_busy_data(payload, source_id, mimo_lease)
        if payload.persist:
            repo.save_extraction_result(assets)
        wardrobe_items = assets.wardrobe_items
        pantry_items = assets.pantry_items
        preferences = assets.preferences
        low_confidence_notes = list(assets.low_confidence_notes)
    else:
        wardrobe_items = repo.list_wardrobe_items()
        pantry_items = repo.list_pantry_items()
        preferences = repo.list_preferences()
        low_confidence_notes = []

    outfit = None
    cooking = None
    if payload.domain == "outfit":
        outfit = _recommend_outfit_from_inventory(
            payload,
            wardrobe_items=wardrobe_items,
            preferences=preferences,
        )
        if outfit is None and not used_visual_input:
            low_confidence_notes.append(
                "No stored wardrobe items are available; ask the user before capturing a camera clip."
            )
    else:
        cooking = _recommend_cooking_from_inventory(
            payload,
            pantry_items=pantry_items,
            preferences=preferences,
        )
        if cooking is None and not used_visual_input:
            low_confidence_notes.append(
                "No stored pantry items are available; ask the user before capturing a fridge or kitchen clip."
            )

    history = None
    recommendation = outfit or cooking
    if payload.persist and recommendation is not None:
        repo.record_recommendation(
            payload.domain,
            recommendation,
            source_id=source_id,
        )
        history = {
            "source_id": source_id,
            "recommendation_history_count": len(repo.list_recommendation_history()),
        }

    return {
        "trigger_source": payload.trigger_source,
        "domain": payload.domain,
        "source_id": source_id,
        "used_visual_input": used_visual_input,
        "camera_required": used_visual_input,
        "outfit": _option_payload(outfit.options[0]) if outfit else None,
        "outfit_broadcast_text": outfit.broadcast_text if outfit else None,
        "cooking": _option_payload(cooking.options[0]) if cooking else None,
        "cooking_broadcast_text": cooking.broadcast_text if cooking else None,
        "low_confidence_notes": low_confidence_notes,
        "history": history,
    }


async def _extract_life_assets_with_mimo_lease(
    observation: VisualObservation,
) -> tuple[LifeExtractionResult | None, str | None, dict[str, Any]]:
    lease = await _MIMO_LEASE_MANAGER.try_acquire("mimo", "visual")
    if not lease.acquired:
        return None, None, _mimo_lease_record(acquired=False, release_reason="busy")
    try:
        assets, raw_mimo_text = await extract_life_assets_with_live_mimo(
            observation=observation,
        )
    except Exception:
        await lease.release(reason="failed")
        raise
    await lease.release(reason="completed")
    return (
        assets,
        raw_mimo_text,
        _mimo_lease_record(
            acquired=True,
            release_reason="completed",
        ),
    )


def _mimo_lease_record(*, acquired: bool, release_reason: str) -> dict[str, Any]:
    return {
        "resource_type": "mimo",
        "resource_id": "visual",
        "acquired": acquired,
        "lease_released": True,
        "release_reason": release_reason,
    }


def _live_mimo_busy_data(
    observation: VisualObservation,
    mimo_lease: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source_id": observation.source_id,
        "mimo_source": "live_mimo_busy",
        "caption": None,
        "visual_source_type": observation.source_type,
        "outfit": None,
        "outfit_broadcast_text": _MIMO_BUSY_MESSAGE,
        "cooking": None,
        "cooking_broadcast_text": _MIMO_BUSY_MESSAGE,
        "low_confidence_notes": [_MIMO_BUSY_MESSAGE],
        "mimo_lease": mimo_lease,
        "reason": "mimo_lease_busy",
    }


def _trigger_mimo_busy_data(
    payload: LifeTriggerPayload,
    source_id: str,
    mimo_lease: dict[str, Any],
) -> dict[str, Any]:
    return {
        "trigger_source": payload.trigger_source,
        "domain": payload.domain,
        "source_id": source_id,
        "used_visual_input": True,
        "camera_required": True,
        "outfit": None,
        "outfit_broadcast_text": _MIMO_BUSY_MESSAGE
        if payload.domain == "outfit"
        else None,
        "cooking": None,
        "cooking_broadcast_text": (
            _MIMO_BUSY_MESSAGE if payload.domain == "cooking" else None
        ),
        "low_confidence_notes": [_MIMO_BUSY_MESSAGE],
        "history": None,
        "mimo_lease": mimo_lease,
        "reason": "mimo_lease_busy",
    }


async def run_life_text_trigger(payload: LifeTextTriggerPayload) -> dict[str, Any]:
    """Classify a speech transcript/command and run life agents only on match."""
    intent = _classify_life_text_intent(payload.text)
    if intent is None:
        return {
            "matched": False,
            "action": "ignored",
            "trigger_source": payload.trigger_source,
            "domain": None,
            "source_id": payload.source_id,
            "camera_required": False,
            "needs_visual_capture": False,
            "matched_terms": [],
            "prompt": None,
            "trigger": None,
            "reason": "No outfit or cooking life-agent intent matched.",
        }

    has_visual_input = bool(payload.clip_base64 or payload.mimo_payload)
    prompt = payload.prompt or intent.prompt
    inferred_occasion = _contextual_life_occasion(payload.text, payload.occasion)
    inferred_weather = infer_life_weather(payload.text, default=payload.weather)
    base_data = {
        "matched": True,
        "trigger_source": payload.trigger_source,
        "domain": intent.domain,
        "source_id": payload.source_id,
        "matched_terms": intent.matched_terms,
        "prompt": prompt,
        "occasion": inferred_occasion,
        "weather": inferred_weather,
    }
    if intent.requires_visual_input and not has_visual_input:
        return {
            **base_data,
            "action": "needs_visual_capture",
            "camera_required": True,
            "needs_visual_capture": True,
            "trigger": None,
            "reason": "The command refers to visible objects, so capture one short camera clip before running the life agent.",
        }

    trigger_data = await run_life_trigger(
        _LifeTriggerAdapter(
            trigger_source=payload.trigger_source,
            domain=intent.domain,
            source_id=payload.source_id,
            prompt=prompt,
            clip_base64=payload.clip_base64,
            mimo_payload=payload.mimo_payload,
            occasion=inferred_occasion,
            weather=inferred_weather,
            people_count=payload.people_count,
            time_budget_minutes=payload.time_budget_minutes,
            persist=payload.persist,
            db_path=payload.db_path,
        )
    )
    return {
        **base_data,
        "action": "triggered",
        "camera_required": trigger_data["camera_required"],
        "needs_visual_capture": False,
        "trigger": trigger_data,
        "reason": "Matched life-agent intent and ran one on-demand trigger.",
    }


def _contextual_life_occasion(text: str, default: str) -> str:
    if default.strip() in {
        "today outing",
        "\u4eca\u5929\u51fa\u95e8",
        "\u4eca\u5929\u65e5\u5e38\u51fa\u95e8",
        "\u65e5\u5e38\u51fa\u95e8",
    }:
        return infer_life_occasion(text, default=default)
    return default


def summarize_life_history(
    *,
    db_path: str,
    domain: LifeDomain | None,
    source_id: str | None,
    limit: int,
) -> dict[str, Any]:
    """Read persisted life-agent recommendation history."""
    summary = LifeRepo(db_path).summarize_recommendation_history(
        domain=domain,
        source_id=source_id,
        limit=limit,
    )
    return {
        "db_path": db_path,
        **({"domain": domain} if domain else {}),
        **({"source_id": source_id} if source_id else {}),
        **summary,
    }


def _classify_life_text_intent(text: str) -> _LifeTextIntent | None:
    normalized = text.strip().lower()
    outfit_terms = _matched_terms(
        normalized,
        (
            *OUTFIT_INITIAL_TERMS,
            "穿搭",
            "搭配",
            "怎么搭",
            "衣服",
            "上衣",
            "裤子",
            "裙子",
            "鞋",
            "外套",
            "这件",
            "穿什么",
            "outfit",
            "clothes",
            "shirt",
        ),
    )
    cooking_terms = _matched_terms(
        normalized,
        (
            *COOKING_INITIAL_TERMS,
            "做饭",
            "做菜",
            "烹饪",
            "吃什么",
            "食材",
            "冰箱",
            "厨房",
            "锅",
            "菜谱",
            "怎么做",
            "下饺子",
            "煮",
            "cooking",
            "cook",
            "fridge",
            "ingredient",
        ),
    )
    if not outfit_terms and not cooking_terms:
        return None

    if outfit_terms and len(outfit_terms) >= len(cooking_terms):
        return _LifeTextIntent(
            domain="outfit",
            requires_visual_input=_contains_any(
                normalized,
                (
                    *VISUAL_REFERENCE_TERMS,
                    "这件",
                    "这个",
                    "手里",
                    "拿着",
                    "看看",
                    "镜头",
                    "身上",
                    "穿着",
                    "拍",
                    "this",
                    "holding",
                    "camera",
                    "look at",
                ),
            ),
            prompt=(
                "Focus on visible clothing, shoes, accessories, worn outfit, "
                "uncertain items, and conservative outfit advice."
            ),
            matched_terms=outfit_terms,
        )

    return _LifeTextIntent(
        domain="cooking",
        requires_visual_input=_contains_any(
            normalized,
            (
                *VISUAL_REFERENCE_TERMS,
                "冰箱",
                "厨房",
                "锅",
                "灶",
                "看看",
                "镜头",
                "拍",
                "手里",
                "锅里",
                "fridge",
                "kitchen",
                "pan",
                "camera",
                "look at",
            ),
        ),
        prompt=(
            "Focus on visible ingredients, fridge items, kitchen tools, cooking "
            "state, uncertainty, and conservative safety-aware cooking advice."
        ),
        matched_terms=cooking_terms,
    )


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _first_outfit_person_id(preferences: list[LifePreference]) -> str | None:
    for preference in preferences:
        if preference.domain == "outfit" and preference.person_id:
            return preference.person_id
    return None


def _recommend_outfit_if_possible(
    payload: LifeLiveDemoPayload,
    assets,
) -> RecommendationResult | None:
    if not assets.wardrobe_items:
        return None
    return recommend_outfit(
        OutfitRecommendationRequest(
            wardrobe_item_ids=[item.id for item in assets.wardrobe_items],
            person_id=_first_outfit_person_id(assets.preferences),
            occasion=payload.occasion,
            weather=payload.weather,
            preference_tags=[],
        ),
        wardrobe_items=assets.wardrobe_items,
        preferences=assets.preferences,
    )


def _recommend_outfit_from_inventory(
    payload: LifeTriggerPayload,
    *,
    wardrobe_items,
    preferences: list[LifePreference],
) -> RecommendationResult | None:
    if not wardrobe_items:
        return None
    return recommend_outfit(
        OutfitRecommendationRequest(
            wardrobe_item_ids=[],
            person_id=_first_outfit_person_id(preferences),
            occasion=payload.occasion,
            weather=payload.weather,
            preference_tags=[],
        ),
        wardrobe_items=wardrobe_items,
        preferences=preferences,
    )


def _recommend_cooking_if_possible(
    payload: LifeLiveDemoPayload,
    assets,
) -> RecommendationResult | None:
    if not assets.pantry_items:
        return None
    return recommend_cooking(
        CookingRecommendationRequest(
            pantry_item_ids=[item.id for item in assets.pantry_items],
            people_count=payload.people_count,
            time_budget_minutes=payload.time_budget_minutes,
            taste_tags=[],
            avoid_tags=[],
        ),
        pantry_items=assets.pantry_items,
        preferences=assets.preferences,
    )


def _recommend_cooking_from_inventory(
    payload: LifeTriggerPayload,
    *,
    pantry_items,
    preferences: list[LifePreference],
) -> RecommendationResult | None:
    if not pantry_items:
        return None
    return recommend_cooking(
        CookingRecommendationRequest(
            pantry_item_ids=[item.id for item in pantry_items],
            people_count=payload.people_count,
            time_budget_minutes=payload.time_budget_minutes,
            taste_tags=[],
            avoid_tags=[],
        ),
        pantry_items=pantry_items,
        preferences=preferences,
    )


def _option_payload(option: RecommendationOption) -> dict[str, Any]:
    return {
        "title": option.title,
        "summary": option.summary,
        "rationale": option.rationale,
        "item_ids": option.item_ids,
        "safety_notes": option.safety_notes,
    }


def _persist_results(
    db_path,
    assets,
    *,
    outfit: RecommendationResult | None,
    cooking: RecommendationResult | None,
) -> dict[str, Any]:
    repo = LifeRepo(db_path or "data/life-demo.db")
    summary = repo.save_extraction_result(assets)
    if outfit is not None:
        repo.record_recommendation("outfit", outfit, source_id=assets.source_id)
    if cooking is not None:
        repo.record_recommendation("cooking", cooking, source_id=assets.source_id)
    summary["recommendation_history_count"] = len(repo.list_recommendation_history())
    return summary
