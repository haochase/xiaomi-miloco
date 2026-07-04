# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Live MiMo adapter for life-agent demo payloads."""

from __future__ import annotations

import base64
import json
from typing import Any

from miloco.life.extractor import LifeExtractionResult
from miloco.life.schema import (
    LifePreference,
    PantryItem,
    WardrobeItem,
)
from miloco.life.visual_input import VisualObservation

_SYSTEM_PROMPT = """You are Miloco Life Agent's multimodal extractor.
Return JSON only, no markdown and no explanation. Keep output compact.
Schema:
{"source_id":"","caption":"","wardrobe":[],"pantry":[],"preferences":[],
"low_confidence_notes":[]}
wardrobe item fields:
id,name,category,colors,material_tags,season_tags,formality,warmth_level,
style_tags,source_type,source_ref,confidence,notes.
Allowed wardrobe.category:
top,bottom,dress,outerwear,shoes,bag,accessory.
pantry item fields:
id,name,category,quantity,unit,storage,freshness,diet_tags,source_type,
source_ref,confidence,notes.
Allowed pantry.category:
vegetable,protein,staple,seasoning,drink,frozen,snack,other.
Use source_type=camera. Do not invent unseen assets. Return at most 5 wardrobe
items and 5 pantry items. Use simplified Chinese for names, colors, notes, and
caption, but keep enum values in English.
If no relevant assets are visible, return empty arrays and short uncertainty
notes.
"""

_CATEGORY_MAP = {
    "shirt": "top",
    "t-shirt": "top",
    "tee": "top",
    "polo": "top",
    "coat": "outerwear",
    "jacket": "outerwear",
    "blazer": "outerwear",
    "pants": "bottom",
    "trousers": "bottom",
    "skirt": "bottom",
    "glasses": "accessory",
}
_WARDROBE_CATEGORIES = {
    "top",
    "bottom",
    "dress",
    "outerwear",
    "shoes",
    "bag",
    "accessory",
}
_PANTRY_CATEGORIES = {
    "vegetable",
    "protein",
    "staple",
    "seasoning",
    "drink",
    "frozen",
    "snack",
    "other",
}
_STORAGE_VALUES = {"fridge", "freezer", "room_temp", "unknown"}
_FRESHNESS_VALUES = {"fresh", "normal", "use_soon", "unknown"}
_SEASON_VALUES = {"spring", "summer", "autumn", "winter"}


async def extract_life_assets_with_live_mimo(
    *,
    observation: VisualObservation,
) -> tuple[LifeExtractionResult, str]:
    """Call the configured MiMo model and normalize its life extraction output."""
    from miloco.life.mimo_client import call_life_mimo_chat

    video_base64 = None
    if observation.content_base64 and observation.source_type == "short_clip":
        video_base64 = _normalize_base64(observation.content_base64)

    raw = await call_life_mimo_chat(
        system_prompt=_SYSTEM_PROMPT,
        user_content=f"source_id={observation.source_id}. {observation.prompt or ''}",
        video_base64=video_base64,
        video_fps=1,
        task="vision",
        max_completion_tokens=1800,
        temperature=0.1,
        timeout=60.0,
    )
    text = _extract_live_mimo_response_text(raw)
    return (
        normalize_live_mimo_life_payload(
            text, fallback_source_id=observation.source_id
        ),
        text,
    )


def _extract_live_mimo_response_text(raw: dict[str, Any]) -> str:
    """Extract assistant text from a MiMo chat response with safe diagnostics."""
    from miloco.perception.engine.omni.omni_client import OmniError

    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OmniError(
            "Live MiMo response did not include choices: "
            f"top_level_keys={_format_keys(raw)}"
        )

    choice = choices[0]
    if not isinstance(choice, dict):
        raise OmniError("Live MiMo response choice must be an object.")

    message = choice.get("message")
    if not isinstance(message, dict):
        raise OmniError(
            "Live MiMo response choice did not include message: "
            f"choice_keys={_format_keys(choice)}"
        )

    text = _message_content_to_text(message.get("content")).strip()
    if text:
        return text

    usage = raw.get("usage")
    usage_keys = _format_keys(usage) if isinstance(usage, dict) else "[]"
    raise OmniError(
        "Live MiMo response had empty content: "
        f"finish_reason={choice.get('finish_reason')}, "
        f"message_keys={_format_keys(message)}, "
        f"choice_keys={_format_keys(choice)}, "
        f"usage_keys={usage_keys}"
    )


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments = []
        for item in content:
            if isinstance(item, str):
                fragments.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    fragments.append(text)
        return "\n".join(fragments)
    return ""


def _format_keys(value: dict[str, Any]) -> str:
    return "[" + ", ".join(sorted(str(key) for key in value)) + "]"


def normalize_live_mimo_life_payload(
    payload: dict[str, Any] | str,
    *,
    fallback_source_id: str = "live_mimo",
) -> LifeExtractionResult:
    """Normalize live MiMo output into the deterministic life schema."""
    data = _load_payload(payload)
    source_id = _clean_text(data.get("source_id")) or fallback_source_id
    low_confidence_notes = _string_list(data.get("low_confidence_notes"))
    wardrobe_items = []
    for idx, raw in enumerate(_list_of_dicts(data.get("wardrobe"))):
        normalized = _normalize_wardrobe_item(raw, source_id, idx)
        if normalized:
            try:
                wardrobe_items.append(WardrobeItem(**normalized))
            except ValueError as exc:
                low_confidence_notes.append(
                    f"Skipped wardrobe item {idx + 1}: {str(exc).splitlines()[0]}"
                )

    pantry_items = []
    for idx, raw in enumerate(_list_of_dicts(data.get("pantry"))):
        normalized = _normalize_pantry_item(raw, source_id, idx)
        if normalized:
            try:
                pantry_items.append(PantryItem(**normalized))
            except ValueError as exc:
                low_confidence_notes.append(
                    f"Skipped pantry item {idx + 1}: {str(exc).splitlines()[0]}"
                )

    preferences = _normalize_preferences(data.get("preferences"))
    return LifeExtractionResult(
        source_id=source_id,
        caption=_clean_text(data.get("caption")),
        wardrobe_items=wardrobe_items,
        pantry_items=pantry_items,
        preferences=preferences,
        low_confidence_notes=low_confidence_notes,
    )


def _load_payload(payload: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    text = payload.strip()
    try:
        from miloco.perception.engine.omni.response_parser import extract_json

        json_text = extract_json(text)
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        from miloco.perception.engine.omni.omni_client import OmniError

        preview = text[:160].replace("\n", " ")
        extracted_chars = len(locals().get("json_text", ""))
        raise OmniError(
            "Live MiMo response was not valid JSON: "
            f"content_chars={len(text)}, extracted_chars={extracted_chars}, "
            f"error_pos={exc.pos}, preview={preview}",
            original=exc,
        ) from exc
    if not isinstance(data, dict):
        from miloco.perception.engine.omni.omni_client import OmniError

        raise OmniError("Live MiMo response JSON must be an object.")
    return data


def _normalize_wardrobe_item(
    raw: dict[str, Any], source_id: str, idx: int
) -> dict[str, Any] | None:
    name = _clean_text(raw.get("name"))
    if not name:
        return None
    category = _clean_text(raw.get("category")) or "accessory"
    category = _CATEGORY_MAP.get(category.lower(), category.lower())
    if category not in _WARDROBE_CATEGORIES:
        category = "accessory"
    return {
        "id": _clean_text(raw.get("id")) or f"live_wardrobe_{idx + 1}",
        "name": name,
        "category": category,
        "colors": _string_list(raw.get("colors")),
        "material_tags": _string_list(raw.get("material_tags")),
        "season_tags": [
            tag for tag in _string_list(raw.get("season_tags")) if tag in _SEASON_VALUES
        ],
        "formality": _normalize_score(raw.get("formality"), default=3),
        "warmth_level": _normalize_score(raw.get("warmth_level"), default=2),
        "style_tags": _string_list(raw.get("style_tags")),
        "source_type": "camera",
        "source_ref": _clean_text(raw.get("source_ref")) or source_id,
        "confidence": _normalize_confidence(raw.get("confidence")),
        "notes": _clean_text(raw.get("notes")),
    }


def _normalize_pantry_item(
    raw: dict[str, Any], source_id: str, idx: int
) -> dict[str, Any] | None:
    name = _clean_text(raw.get("name"))
    if not name:
        return None
    category = (_clean_text(raw.get("category")) or "other").lower()
    storage = (_clean_text(raw.get("storage")) or "unknown").lower()
    freshness = (_clean_text(raw.get("freshness")) or "unknown").lower()
    return {
        "id": _clean_text(raw.get("id")) or f"live_pantry_{idx + 1}",
        "name": name,
        "category": category if category in _PANTRY_CATEGORIES else "other",
        "quantity": raw.get("quantity")
        if isinstance(raw.get("quantity"), int | float)
        else None,
        "unit": _clean_text(raw.get("unit")),
        "storage": storage if storage in _STORAGE_VALUES else "unknown",
        "expires_at": _clean_text(raw.get("expires_at")),
        "freshness": freshness if freshness in _FRESHNESS_VALUES else "unknown",
        "diet_tags": _string_list(raw.get("diet_tags")),
        "source_type": "camera",
        "source_ref": _clean_text(raw.get("source_ref")) or source_id,
        "confidence": _normalize_confidence(raw.get("confidence")),
        "notes": _clean_text(raw.get("notes")),
    }


def _normalize_preferences(value: Any) -> list[LifePreference]:
    if isinstance(value, list):
        result = []
        for raw in value:
            if isinstance(raw, dict):
                try:
                    result.append(LifePreference(**raw))
                except ValueError:
                    continue
        return result
    if not isinstance(value, dict):
        return []

    preferences = []
    style_tags = _string_list(value.get("style"))
    if style_tags:
        preferences.append(LifePreference(domain="outfit", tags=style_tags))
    diet_tags = [tag for tag in _string_list(value.get("diet")) if tag != "unknown"]
    if diet_tags:
        preferences.append(LifePreference(domain="cooking", tags=diet_tags))
    return preferences


def _normalize_score(value: Any, *, default: int) -> int:
    if isinstance(value, str):
        mapped = {
            "very casual": 1,
            "casual": 2,
            "business casual": 3,
            "formal": 4,
            "very formal": 5,
        }.get(value.strip().lower())
        if mapped is not None:
            return mapped
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = default
    return min(5, max(1, score))


def _normalize_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.5
    return min(1.0, max(0.0, confidence))


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = []
    return [text for item in raw_values if (text := _clean_text(item))]


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_base64(value: str) -> str:
    if "," in value and value.lstrip().startswith("data:"):
        return value.split(",", 1)[1]
    base64.b64decode(value, validate=True)
    return value
