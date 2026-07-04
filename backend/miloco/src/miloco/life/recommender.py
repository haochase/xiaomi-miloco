# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Deterministic life-domain recommendation helpers for hackathon demos."""

from __future__ import annotations

import re

from miloco.life.outfit_knowledge import build_outfit_style_advice
from miloco.life.schema import (
    CookingRecommendationRequest,
    LifePreference,
    OutfitRecommendationRequest,
    PantryItem,
    RecommendationOption,
    RecommendationResult,
    WardrobeItem,
)


def recommend_outfit(
    request: OutfitRecommendationRequest,
    *,
    wardrobe_items: list[WardrobeItem],
    preferences: list[LifePreference] | None = None,
) -> RecommendationResult:
    """Recommend a simple outfit from extracted wardrobe assets."""
    selected = _select_wardrobe_items(request.wardrobe_item_ids, wardrobe_items)
    if not request.wardrobe_item_ids:
        selected = _select_outfit_set(selected)
    title = _join_item_names(selected, localize=True) or "穿搭建议"
    localized_occasion = _localize_occasion(request.occasion)
    localized_weather = _localize_weather(request.weather) if request.weather else None
    preference_tags = _domain_preference_tags("outfit", preferences)
    style_advice = build_outfit_style_advice(
        occasion=request.occasion,
        weather=request.weather,
        preference_tags=[*request.preference_tags, *preference_tags],
    )
    rationale = [
        f"适合场景：{localized_occasion}",
        "基于当前已识别到的衣橱物品生成。",
    ]
    if localized_weather:
        rationale.append(f"考虑天气/环境：{localized_weather}")
    if request.preference_tags or preference_tags:
        tags = "、".join(
            _localize_style_tags(
                _unique_tags([*request.preference_tags, *preference_tags])
            )
        )
        rationale.append(f"参考风格偏好：{tags}")
    if style_advice.summary:
        rationale.append(f"匹配穿搭策略：{style_advice.summary}")
    rationale.extend(style_advice.rationale)

    summary = f"建议{localized_occasion}优先考虑{title}。"
    option = RecommendationOption(
        title=title,
        summary=summary,
        rationale=rationale,
        item_ids=[item.id for item in selected],
        safety_notes=[],
    )
    return RecommendationResult(
        domain="outfit",
        options=[option],
        broadcast_text=_outfit_broadcast_text(
            occasion=request.occasion,
            weather=request.weather,
            title=title,
            style_hint=style_advice.broadcast_hint,
        ),
    )


def recommend_cooking(
    request: CookingRecommendationRequest,
    *,
    pantry_items: list[PantryItem],
    preferences: list[LifePreference] | None = None,
) -> RecommendationResult:
    """Recommend a conservative cooking plan from extracted pantry assets."""
    selected = _select_pantry_items(request.pantry_item_ids, pantry_items)
    title = _cooking_title(selected)
    preference_tags = _domain_preference_tags("cooking", preferences)
    item_names = _join_item_names(selected, localize=True)
    taste_tags = (
        ", ".join(_unique_tags([*request.taste_tags, *preference_tags])) or "balanced"
    )

    option = RecommendationOption(
        title=title,
        summary=(
            f"可以用{item_names}给 {request.people_count} 人做一份简单晚餐，"
            f"预计约 {request.time_budget_minutes} 分钟。"
        ),
        rationale=[
            "Uses pantry items already extracted from the mock MiMo payload.",
            f"Fits taste target: {taste_tags}.",
            "Keeps the plan simple enough for the demo dinner flow.",
        ],
        item_ids=[item.id for item in selected],
        safety_notes=[
            "Water may be boiling; please confirm before adding dumplings.",
            "Please check food state yourself before serving.",
        ],
    )
    return RecommendationResult(
        domain="cooking",
        options=[option],
        broadcast_text=(
            f"今晚可以考虑{title}。请先确认锅具状态和食材新鲜度，出锅前再自行检查熟度。"
        ),
    )


def _select_wardrobe_items(
    requested_ids: list[str], wardrobe_items: list[WardrobeItem]
) -> list[WardrobeItem]:
    if not requested_ids:
        return [item for item in wardrobe_items if item.status in {"active", "unknown"}]
    by_id = {item.id: item for item in wardrobe_items}
    return [by_id[item_id] for item_id in requested_ids if item_id in by_id]


def _select_outfit_set(items: list[WardrobeItem]) -> list[WardrobeItem]:
    category_order = [
        "outerwear",
        "top",
        "bottom",
        "dress",
        "shoes",
        "bag",
        "accessory",
    ]
    selected: list[WardrobeItem] = []
    used_name_keys: set[str] = set()
    for category in category_order:
        item = _first_item_for_category(items, category, used_name_keys)
        if item is None:
            continue
        selected.append(item)
        used_name_keys.add(_name_key(_localize_outfit_name(item.name)))
    return selected or items[:3]


def _first_item_for_category(
    items: list[WardrobeItem],
    category: str,
    used_name_keys: set[str],
) -> WardrobeItem | None:
    for item in items:
        if item.category != category:
            continue
        if _name_key(_localize_outfit_name(item.name)) in used_name_keys:
            continue
        return item
    return None


def _select_pantry_items(
    requested_ids: list[str], pantry_items: list[PantryItem]
) -> list[PantryItem]:
    by_id = {item.id: item for item in pantry_items}
    return [by_id[item_id] for item_id in requested_ids if item_id in by_id]


def _domain_preference_tags(
    domain: str, preferences: list[LifePreference] | None
) -> list[str]:
    return [
        tag
        for preference in preferences or []
        if preference.domain == domain
        for tag in preference.tags
    ]


def _join_item_names(
    items: list[WardrobeItem] | list[PantryItem],
    *,
    localize: bool = False,
    max_items: int | None = None,
) -> str:
    names = []
    seen_keys = set()
    for item in items:
        if localize and isinstance(item, PantryItem):
            name = _localize_food_name(item.name)
        elif localize and isinstance(item, WardrobeItem):
            name = _localize_outfit_name(item.name)
        else:
            name = item.name
        key = _name_key(name)
        if name and key not in seen_keys:
            names.append(name)
            seen_keys.add(key)
        if max_items is not None and len(names) >= max_items:
            break
    separator = "、" if localize else ", "
    return separator.join(names)


def _name_key(name: str) -> str:
    return re.sub(r"[\s,，、。.!！?？（）()]+", "", name.strip().lower())


def _cooking_title(items: list[PantryItem]) -> str:
    names = {item.name for item in items}
    if {"eggs", "tomatoes"}.issubset(names) and "frozen dumplings" in names:
        return "番茄鸡蛋配速冻饺子"
    return _join_item_names(items, localize=True) or "简单晚餐方案"


def _outfit_broadcast_text(
    *,
    occasion: str,
    weather: str | None,
    title: str,
    style_hint: str | None = None,
) -> str:
    localized_occasion = _localize_occasion(occasion)
    localized_title = _localize_outfit_title(title)
    if style_hint:
        return f"穿搭建议：{localized_occasion}，优先{localized_title}。重点是{style_hint}。"
    text = (
        f"穿搭建议：{localized_occasion}优先{localized_title}；"
        f"{_generic_outfit_strategy(localized_title)}。"
    )
    if weather and not _is_weather_placeholder(weather):
        text += (
            f"当前天气或环境是{_localize_weather(weather)}，可以根据体感再加减外套。"
        )
    return text


def _is_weather_placeholder(weather: str) -> bool:
    normalized = weather.strip().lower()
    return normalized in {
        "请按今天当地天气给出保守建议",
        "按今天当地天气给出保守建议",
        "today local weather",
        "local weather",
    }


def _generic_outfit_strategy(localized_title: str) -> str:
    if "外套" in localized_title and "长裤" in localized_title:
        if "包" in localized_title:
            return "先让外套和长裤定基调，包只做功能补充"
        return "先让外套和长裤定基调，内搭保持干净"
    if "外套" in localized_title:
        return "先让外套定整体风格，内搭保持清爽"
    if "衬衫" in localized_title or "Polo" in localized_title:
        return "先让上半身保持利落，再按体感加外层"
    return "先让主色稳定，再按目的地调整层次"


def _localize_outfit_title(title: str) -> str:
    parts = [part.strip() for part in title.split(",") if part.strip()]
    if not parts:
        return "当前可见衣物"
    return "、".join(_localize_outfit_name(part) for part in parts)


def _localize_outfit_name(name: str) -> str:
    normalized = name.strip().lower()
    if _contains_cjk(name):
        return _remove_spaces_between_cjk(" ".join(name.strip().split()))
    replacements = [
        ("dark gray", "深灰色"),
        ("dark grey", "深灰色"),
        ("light gray", "浅灰色"),
        ("light grey", "浅灰色"),
        ("gray", "灰色"),
        ("grey", "灰色"),
        ("dark blue", "深蓝色"),
        ("navy blue", "藏蓝色"),
        ("light blue", "浅蓝色"),
        ("blue", "蓝色"),
        ("white", "白色"),
        ("black", "黑色"),
        ("red", "红色"),
        ("green", "绿色"),
        ("brown", "棕色"),
        ("orange", "橙色"),
        ("yellow", "黄色"),
        ("purple", "紫色"),
        ("pink", "粉色"),
        ("beige", "米色"),
        ("khaki", "卡其色"),
        ("cream", "奶油色"),
        ("plaid", "格纹"),
        ("checked", "格纹"),
        ("portugal", "葡萄牙"),
        ("sports", "运动"),
        ("sport", "运动"),
        ("football", "足球"),
        ("soccer", "足球"),
        ("dress shirts", "正装衬衫"),
        ("dress shirt", "正装衬衫"),
        ("short-sleeved button-down shirts", "短袖扣领衬衫"),
        ("short-sleeved button-down shirt", "短袖扣领衬衫"),
        ("short sleeve button-down shirts", "短袖扣领衬衫"),
        ("short sleeve button-down shirt", "短袖扣领衬衫"),
        ("button-down shirts", "扣领衬衫"),
        ("button-down shirt", "扣领衬衫"),
        ("button down shirts", "扣领衬衫"),
        ("button down shirt", "扣领衬衫"),
        ("long-sleeved", "长袖"),
        ("long sleeved", "长袖"),
        ("long sleeve", "长袖"),
        ("short-sleeved", "短袖"),
        ("short sleeved", "短袖"),
        ("short sleeve", "短袖"),
        ("blazer", "西装外套"),
        ("suit jackets", "西装外套"),
        ("suit jacket", "西装外套"),
        ("sports jerseys", "运动球衣"),
        ("sports jersey", "运动球衣"),
        ("jerseys", "球衣"),
        ("jersey", "球衣"),
        ("t-shirts", "T恤"),
        ("t-shirt", "T恤"),
        ("tee shirts", "T恤"),
        ("tee shirt", "T恤"),
        ("polo shirts", "Polo衫"),
        ("polo shirt", "Polo衫"),
        ("polo", "Polo衫"),
        ("shirts", "衬衫"),
        ("shirt", "衬衫"),
        ("jackets", "外套"),
        ("jacket", "外套"),
        ("coats", "大衣"),
        ("coat", "大衣"),
        ("pants", "长裤"),
        ("trousers", "长裤"),
        ("shorts", "短裤"),
        ("jeans", "牛仔裤"),
        ("skirts", "裙子"),
        ("skirt", "裙子"),
        ("dresses", "连衣裙"),
        ("dress", "连衣裙"),
        ("shoes", "鞋子"),
        ("shoe", "鞋子"),
        ("sneakers", "运动鞋"),
        ("sneaker", "运动鞋"),
        ("bags", "包"),
        ("bag", "包"),
        ("backpacks", "双肩包"),
        ("backpack", "双肩包"),
        ("sweaters", "毛衣"),
        ("sweater", "毛衣"),
        ("hoodies", "卫衣"),
        ("hoodie", "卫衣"),
        ("sweatshirts", "卫衣"),
        ("sweatshirt", "卫衣"),
        ("vests", "马甲"),
        ("vest", "马甲"),
        ("caps", "帽子"),
        ("cap", "帽子"),
        ("hats", "帽子"),
        ("hat", "帽子"),
        ("scarves", "围巾"),
        ("scarf", "围巾"),
        ("glasses", "眼镜"),
        ("accessories", "配饰"),
        ("worn", "已穿在身上"),
    ]
    localized = normalized
    for source, target in replacements:
        localized = localized.replace(source, target)
    localized = " ".join(localized.split())
    localized = localized.replace(" 已穿在身上", "（已穿在身上）")
    localized = _remove_spaces_between_cjk(localized)
    return localized if localized != normalized else name


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _localize_occasion(occasion: str) -> str:
    normalized = occasion.strip().lower()
    mapping = {
        "today home-office video call": "今天居家办公的视频会议",
        "tomorrow morning interview": "明天上午面试",
        "video meeting": "视频会议",
        "client meeting": "客户会议",
        "morning commute": "早晨通勤",
        "08:30 outfit reminder": "早上八点半穿搭提醒",
        "today outing": "今天出门",
        "today soccer outing": "今天出门踢足球",
        "今晚和朋友吃饭": "今晚和朋友吃饭",
        "社交聚餐": "社交聚餐",
    }
    return mapping.get(normalized, occasion)


def _localize_weather(weather: str) -> str:
    normalized = weather.strip().lower()
    mapping = {
        "cool and cloudy": "偏凉多云",
        "indoor": "室内环境",
        "cool rainy morning": "偏凉、有雨的早晨",
        "warm sunny morning": "温暖晴朗的早晨",
        "warm indoor summer evening": "温暖的夏季室内环境",
        "rainy evening": "有雨的傍晚",
    }
    return mapping.get(normalized, weather)


def _localize_style_tags(tags: list[str]) -> list[str]:
    mapping = {
        "casual": "休闲",
        "sporty": "运动",
        "formal": "正式",
        "business": "商务",
        "not flashy": "不夸张",
        "formal enough": "正式感足够",
        "comfortable": "舒适",
        "simple": "简洁",
        "summer": "夏季",
        "all": "四季",
    }
    return [mapping.get(tag.strip().lower(), tag) for tag in tags]


def _remove_spaces_between_cjk(text: str) -> str:
    text = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", text)
    for left in (
        "色",
        "灰",
        "蓝",
        "白",
        "黑",
        "红",
        "绿",
        "米",
        "棕",
        "橙",
        "黄",
        "紫",
        "粉",
        "卡",
        "奶",
    ):
        text = text.replace(f"{left} ", left)
    return text


def _localize_food_name(name: str) -> str:
    normalized = name.strip().lower()
    mapping = {
        "egg": "鸡蛋",
        "eggs": "鸡蛋",
        "tomato": "番茄",
        "tomatoes": "番茄",
        "broccoli": "西兰花",
        "greens": "绿叶菜",
        "vegetable": "蔬菜",
        "vegetables": "蔬菜",
        "potato": "土豆",
        "potatoes": "土豆",
        "carrot": "胡萝卜",
        "carrots": "胡萝卜",
        "frozen dumpling": "速冻饺子",
        "frozen dumplings": "速冻饺子",
        "cooking oil": "食用油",
        "seasoning": "调料",
        "tea pot": "茶壶",
        "teapot": "茶壶",
    }
    return mapping.get(normalized, name)


def _unique_tags(tags: list[str]) -> list[str]:
    seen = set()
    unique = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique.append(tag)
    return unique
