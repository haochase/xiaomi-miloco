# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Recommendation engine tests for the life domain demo."""

from __future__ import annotations

import json
from pathlib import Path

from miloco.life.extractor import extract_life_assets_from_mimo_mock
from miloco.life.recommender import recommend_cooking, recommend_outfit
from miloco.life.schema import (
    CookingRecommendationRequest,
    OutfitRecommendationRequest,
    WardrobeItem,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _demo_assets():
    payload = json.loads((FIXTURE_DIR / "life_mimo_mock.json").read_text())
    return extract_life_assets_from_mimo_mock(payload)


def test_recommends_interview_outfit_from_extracted_assets():
    assets = _demo_assets()
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=["blazer_gray", "shirt_white"],
        person_id="adult_a",
        occasion="tomorrow morning interview",
        weather="cool and cloudy",
        preference_tags=["not flashy"],
    )

    result = recommend_outfit(
        request,
        wardrobe_items=assets.wardrobe_items,
        preferences=assets.preferences,
    )

    assert result.domain == "outfit"
    assert result.options[0].item_ids == ["blazer_gray", "shirt_white"]
    assert result.options[0].title == "深灰色西装外套、白色衬衫"
    assert "明天上午面试" in result.options[0].summary
    assert "interview" not in result.options[0].summary.lower()
    assert "参考风格偏好：不夸张、正式感足够" in result.options[0].rationale
    assert result.broadcast_text is not None
    assert "穿搭建议" in result.broadcast_text
    assert "深灰色西装外套、白色衬衫" in result.broadcast_text
    assert "For " not in result.broadcast_text
    assert "try " not in result.broadcast_text


def test_recommends_outfit_localizes_plural_clothing_and_colors_to_chinese():
    item = WardrobeItem(
        id="shirt_black",
        name="black shirts",
        category="top",
        colors=["black"],
        formality=2,
        warmth_level=1,
        source_type="camera",
        confidence=0.9,
    )
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=["shirt_black"],
        occasion="video meeting",
        weather="indoor",
    )

    result = recommend_outfit(request, wardrobe_items=[item])

    option = result.options[0]
    assert option.title == "黑色衬衫"
    assert "黑色衬衫" in option.summary
    assert "视频会议" in option.summary
    assert result.broadcast_text is not None
    assert "黑色衬衫" in result.broadcast_text
    assert "black" not in option.title.lower()
    assert "shirts" not in option.title.lower()
    assert "black" not in result.broadcast_text.lower()
    assert "shirts" not in result.broadcast_text.lower()


def test_recommends_outfit_dedupes_repeated_inventory_names_for_speech():
    items = [
        WardrobeItem(
            id="jacket_1",
            name="blue sports jacket",
            category="outerwear",
            colors=["blue"],
            formality=1,
            warmth_level=2,
            source_type="manual",
            confidence=0.9,
        ),
        WardrobeItem(
            id="shirt_1",
            name="white plaid shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="manual",
            confidence=0.9,
        ),
        WardrobeItem(
            id="jacket_2",
            name="blue sports jacket",
            category="outerwear",
            colors=["blue"],
            formality=1,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="shirt_2",
            name="white plaid shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=["jacket_1", "shirt_1", "jacket_2", "shirt_2"],
        occasion="today outing",
        weather=None,
    )

    result = recommend_outfit(request, wardrobe_items=items)

    option = result.options[0]
    assert option.title.count("蓝色运动外套") == 1
    assert option.title.count("白色格纹衬衫") == 1
    assert result.broadcast_text is not None
    assert result.broadcast_text.count("蓝色运动外套") == 1
    assert result.broadcast_text.count("白色格纹衬衫") == 1
    assert len(result.broadcast_text) <= 80


def test_recommends_outfit_generic_today_outing_adds_actionable_strategy():
    items = [
        WardrobeItem(
            id="jacket_blue",
            name="blue sports jacket",
            category="outerwear",
            colors=["blue"],
            formality=1,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="hoodie_orange",
            name="orange hoodie",
            category="top",
            colors=["orange"],
            formality=1,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="pants_gray",
            name="gray trousers",
            category="bottom",
            colors=["gray"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="backpack_black",
            name="black backpack",
            category="bag",
            colors=["black"],
            formality=1,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="today outing",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "今天出门" in result.broadcast_text
    assert "先让外套和长裤定基调" in result.broadcast_text
    assert "包只做功能补充" in result.broadcast_text
    assert "当前天气或环境是" not in result.broadcast_text
    assert len(result.broadcast_text) <= 100


def test_recommends_outfit_generic_today_outing_skips_weather_placeholder():
    items = [
        WardrobeItem(
            id="jacket_blue",
            name="blue sports jacket",
            category="outerwear",
            colors=["blue"],
            formality=1,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="hoodie_orange",
            name="orange hoodie",
            category="top",
            colors=["orange"],
            formality=1,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="pants_gray",
            name="gray trousers",
            category="bottom",
            colors=["gray"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="backpack_black",
            name="black backpack",
            category="bag",
            colors=["black"],
            formality=1,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="今天日常出门",
        weather="请按今天当地天气给出保守建议",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "先让外套和长裤定基调" in result.broadcast_text
    assert "包只做功能补充" in result.broadcast_text
    assert "当前天气或环境是" not in result.broadcast_text
    assert "请按今天当地天气" not in result.broadcast_text
    assert len(result.broadcast_text) <= 100


def test_recommends_outfit_speaks_one_wearable_set_not_inventory_list():
    items = [
        WardrobeItem(
            id="jacket_blue",
            name="blue sports jacket",
            category="outerwear",
            colors=["blue"],
            formality=1,
            warmth_level=2,
            source_type="manual",
            confidence=0.9,
        ),
        WardrobeItem(
            id="jacket_green",
            name="green jacket",
            category="outerwear",
            colors=["green"],
            formality=1,
            warmth_level=2,
            source_type="manual",
            confidence=0.9,
        ),
        WardrobeItem(
            id="shirt_white",
            name="white plaid shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="manual",
            confidence=0.9,
        ),
        WardrobeItem(
            id="shirt_green",
            name="green shirt",
            category="top",
            colors=["green"],
            formality=2,
            warmth_level=1,
            source_type="manual",
            confidence=0.9,
        ),
        WardrobeItem(
            id="pants_gray",
            name="light gray trousers",
            category="bottom",
            colors=["gray"],
            formality=2,
            warmth_level=1,
            source_type="manual",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="today outing",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    option = result.options[0]
    assert option.title == "蓝色运动外套、白色格纹衬衫、浅灰色长裤"
    assert "绿色外套" not in option.title
    assert "绿色衬衫" not in option.title
    assert result.broadcast_text is not None
    assert "绿色外套" not in result.broadcast_text
    assert "绿色衬衫" not in result.broadcast_text


def test_recommends_outfit_localizes_worn_clothing_status_naturally():
    item = WardrobeItem(
        id="shirt_worn",
        name="white t-shirts worn",
        category="top",
        colors=["white"],
        formality=1,
        warmth_level=1,
        source_type="camera",
        confidence=0.9,
    )
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=["shirt_worn"],
        occasion="video meeting",
        weather="indoor",
    )

    result = recommend_outfit(request, wardrobe_items=[item])

    assert result.options[0].title == "白色T恤（已穿在身上）"
    assert "worn" not in result.options[0].title.lower()
    assert result.broadcast_text is not None
    assert "worn" not in result.broadcast_text.lower()


def test_recommends_outfit_adds_rainy_commute_strategy():
    items = [
        WardrobeItem(
            id="jacket_navy",
            name="navy blue jacket",
            category="outerwear",
            colors=["blue"],
            formality=2,
            warmth_level=2,
            source_type="manual",
            confidence=0.9,
        ),
        WardrobeItem(
            id="shirt_white",
            name="white shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="manual",
            confidence=0.9,
        ),
        WardrobeItem(
            id="pants_gray",
            name="gray trousers",
            category="bottom",
            colors=["gray"],
            formality=2,
            warmth_level=1,
            source_type="manual",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="morning commute",
        weather="cool rainy morning",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "雨天通勤" in " ".join(result.options[0].rationale)
    assert "防滑、耐脏和可脱换外层" in result.broadcast_text
    for english in ("rainy", "commute", "jacket", "shirt"):
        assert english not in result.broadcast_text.lower()


def test_recommends_outfit_matches_chinese_natural_weather_and_occasion_text():
    item = WardrobeItem(
        id="shirt_white",
        name="white shirt",
        category="top",
        colors=["white"],
        formality=2,
        warmth_level=1,
        source_type="manual",
        confidence=0.9,
    )
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=["shirt_white"],
        occasion="今天下雨天通勤上班",
        weather="南方夏天闷热有雨",
    )

    result = recommend_outfit(request, wardrobe_items=[item])

    assert result.broadcast_text is not None
    assert "防滑、耐脏和可脱换外层" in result.broadcast_text
    assert "轻薄透气" in result.broadcast_text or "透气" in " ".join(
        result.options[0].rationale
    )


def test_recommends_outfit_localizes_soccer_outing_terms_to_chinese():
    items = [
        WardrobeItem(
            id="portugal_jersey",
            name="portugal soccer jersey",
            category="top",
            colors=["red"],
            formality=1,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="button_down",
            name="white short-sleeved button-down shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=["portugal_jersey", "button_down"],
        occasion="today soccer outing",
        weather=None,
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.options[0].title == "葡萄牙足球球衣、白色短袖扣领衬衫"
    assert result.broadcast_text is not None
    assert "今天出门踢足球" in result.broadcast_text
    assert "运动场景优先排汗和活动空间" in result.broadcast_text
    assert "会议" not in result.broadcast_text
    for english in ("portugal", "soccer", "short-sleeved", "button-down"):
        assert english not in result.broadcast_text.lower()


def test_recommends_outfit_handles_rainy_soccer_outing():
    items = [
        WardrobeItem(
            id="portugal_jersey",
            name="portugal soccer jersey",
            category="top",
            colors=["red"],
            formality=1,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="jacket_blue",
            name="blue sports jacket",
            category="outerwear",
            colors=["blue"],
            formality=1,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="shorts_orange",
            name="orange shorts",
            category="bottom",
            colors=["orange"],
            formality=1,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="今天出门踢足球",
        weather="今天下雨，场地可能有点湿滑",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "雨天运动出行" in result.broadcast_text
    assert "鞋底抓地防滑" in result.broadcast_text
    assert "快干透气" in result.broadcast_text
    assert "备用上衣" in result.broadcast_text
    assert "通勤" not in result.broadcast_text
    assert "会议" not in result.broadcast_text
    assert "社交" not in result.broadcast_text


def test_recommends_outfit_keeps_humid_social_dinner_context():
    items = [
        WardrobeItem(
            id="jacket_blue",
            name="blue sports jacket",
            category="outerwear",
            colors=["blue"],
            formality=1,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="shirt_purple",
            name="purple long-sleeved shirt",
            category="top",
            colors=["purple"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="shorts_orange",
            name="orange shorts",
            category="bottom",
            colors=["orange"],
            formality=1,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="今晚和朋友吃饭",
        weather="闷热潮湿",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "今晚和朋友吃饭" in result.broadcast_text
    assert "社交场景可以有一个亮点单品" in result.broadcast_text
    assert "轻薄透气" in result.broadcast_text or "透气" in " ".join(
        result.options[0].rationale
    )
    assert "今天出门" not in result.broadcast_text
    assert "会议" not in result.broadcast_text


def test_recommends_outfit_keeps_existing_chinese_clothing_names_stable():
    item = WardrobeItem(
        id="polo_white",
        name="白色短袖Polo衫",
        category="top",
        colors=["white"],
        formality=1,
        warmth_level=1,
        source_type="camera",
        confidence=0.9,
    )
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=["polo_white"],
        occasion="video meeting",
        weather="indoor",
    )

    result = recommend_outfit(request, wardrobe_items=[item])

    assert result.options[0].title == "白色短袖Polo衫"
    assert "Polo衫衫" not in result.options[0].title
    assert result.broadcast_text is not None
    assert "Polo衫衫" not in result.broadcast_text


def test_recommends_outfit_prioritizes_video_meeting_under_indoor_ac():
    items = [
        WardrobeItem(
            id="shirt_white",
            name="white shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="jacket_navy",
            name="navy blue jacket",
            category="outerwear",
            colors=["blue"],
            formality=2,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="下午视频会议",
        weather="室内空调有点冷",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "下午视频会议" in result.broadcast_text
    assert "视频场景重点看上半身" in result.broadcast_text
    assert "颜色要和背景拉开一点" in result.broadcast_text
    assert "利落锚点" in " ".join(result.options[0].rationale)
    assert "工作场景保留一个利落锚点" not in result.broadcast_text
    for english in ("white", "shirt", "navy", "jacket"):
        assert english not in result.broadcast_text.lower()


def test_recommends_outfit_prioritizes_rainy_client_meeting():
    items = [
        WardrobeItem(
            id="shirt_white",
            name="white shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="jacket_navy",
            name="navy blue jacket",
            category="outerwear",
            colors=["blue"],
            formality=2,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="pants_gray",
            name="gray trousers",
            category="bottom",
            colors=["gray"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="今天见客户开会",
        weather="有雨、闷热潮湿",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "今天见客户开会" in result.broadcast_text
    assert "雨天见客户或开会" in result.broadcast_text
    assert "鞋履防滑耐脏" in result.broadcast_text
    assert "上半身保持利落" in result.broadcast_text
    assert "轻薄透气" in result.broadcast_text or "透气" in " ".join(
        result.options[0].rationale
    )
    assert "社交场景" not in result.broadcast_text
    for english in ("white", "shirt", "navy", "jacket"):
        assert english not in result.broadcast_text.lower()


def test_recommends_outfit_prioritizes_southern_humid_client_commute():
    items = [
        WardrobeItem(
            id="shirt_white",
            name="white shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="jacket_navy",
            name="navy blue jacket",
            category="outerwear",
            colors=["blue"],
            formality=2,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="pants_gray",
            name="gray trousers",
            category="bottom",
            colors=["gray"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="今天见客户开会",
        weather="南方夏季湿热通勤",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "今天见客户开会" in result.broadcast_text
    assert "南方湿热通勤后见客户" in result.broadcast_text
    assert "内搭轻薄透气" in result.broadcast_text
    assert "利落外层稳住形象" in result.broadcast_text
    assert "社交场景" not in result.broadcast_text
    assert "雨天见客户" not in result.broadcast_text
    for english in ("white", "shirt", "navy", "jacket"):
        assert english not in result.broadcast_text.lower()


def test_recommends_outfit_avoids_heavy_outerwear_for_humid_client_commute():
    items = [
        WardrobeItem(
            id="shirt_white",
            name="white shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="coat_black",
            name="black coat",
            category="outerwear",
            colors=["black"],
            formality=2,
            warmth_level=3,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="pants_gray",
            name="gray trousers",
            category="bottom",
            colors=["gray"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="今天通勤后见客户开会",
        weather="深圳夏天闷热潮湿",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "南方湿热通勤后见客户" in result.broadcast_text
    assert "不要选厚重外套" in result.broadcast_text
    assert "雨天见客户" not in result.broadcast_text
    assert "社交场景" not in result.broadcast_text


def test_recommends_outfit_handles_vague_bad_weather_client_commute():
    items = [
        WardrobeItem(
            id="shirt_white",
            name="white shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="jacket_navy",
            name="navy blue jacket",
            category="outerwear",
            colors=["blue"],
            formality=2,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="pants_gray",
            name="gray trousers",
            category="bottom",
            colors=["gray"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="今天通勤后见客户开会",
        weather="天气不好，阴天",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "天气不稳定通勤见客户" in result.broadcast_text
    assert "轻便耐脏外层" in result.broadcast_text
    assert "鞋子稳一点" in result.broadcast_text
    assert "雨天见客户" not in result.broadcast_text
    assert "南方湿热通勤" not in result.broadcast_text
    assert "社交场景" not in result.broadcast_text


def test_recommends_outfit_keeps_client_commute_broadcast_concise():
    items = [
        WardrobeItem(
            id="shirt_white",
            name="white shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="jacket_navy",
            name="navy blue jacket",
            category="outerwear",
            colors=["blue"],
            formality=2,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="pants_gray",
            name="gray trousers",
            category="bottom",
            colors=["gray"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="今天通勤后见客户开会",
        weather="天气不好，阴天",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert len(result.broadcast_text) <= 96
    assert "天气不稳定通勤见客户" in result.broadcast_text
    assert "轻便耐脏外层" in result.broadcast_text
    assert "鞋子稳一点" in result.broadcast_text
    assert "当前天气或环境是" not in result.broadcast_text


def test_recommends_outfit_handles_humid_commute_indoor_ac_transition():
    items = [
        WardrobeItem(
            id="shirt_white",
            name="white shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="jacket_navy",
            name="navy blue jacket",
            category="outerwear",
            colors=["blue"],
            formality=2,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="pants_gray",
            name="gray trousers",
            category="bottom",
            colors=["gray"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="今天通勤上班",
        weather="广州夏天外面闷热潮湿，办公室空调有点冷",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "外面湿热室内空调" in result.broadcast_text
    assert "贴身层透气排汗" in result.broadcast_text
    assert "薄外层方便穿脱" in result.broadcast_text
    assert "客户" not in result.broadcast_text
    assert "视频" not in result.broadcast_text
    assert "社交场景" not in result.broadcast_text


def test_recommends_outfit_handles_humid_commute_to_social_dinner_transition():
    items = [
        WardrobeItem(
            id="shirt_purple",
            name="purple long-sleeved shirt",
            category="top",
            colors=["purple"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="jacket_blue",
            name="blue sports jacket",
            category="outerwear",
            colors=["blue"],
            formality=1,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="shorts_orange",
            name="orange shorts",
            category="bottom",
            colors=["orange"],
            formality=1,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="今天通勤上班，晚上和朋友吃饭",
        weather="深圳夏天外面闷热潮湿",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "湿热通勤后晚间社交" in result.broadcast_text
    assert "先透气排汗" in result.broadcast_text
    assert "晚餐保留一个亮点" in result.broadcast_text
    assert "客户" not in result.broadcast_text
    assert "视频" not in result.broadcast_text
    assert "雨天" not in result.broadcast_text


def test_recommends_outfit_handles_jiangnan_plum_rain_cool_commute():
    items = [
        WardrobeItem(
            id="shirt_white",
            name="white shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="jacket_navy",
            name="navy blue jacket",
            category="outerwear",
            colors=["blue"],
            formality=2,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="pants_gray",
            name="gray trousers",
            category="bottom",
            colors=["gray"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="今天通勤上班",
        weather="上海江南梅雨季有点湿冷",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "江南梅雨湿冷通勤" in result.broadcast_text
    assert "外层防风防潮" in result.broadcast_text
    assert "鞋底防滑" in result.broadcast_text
    assert "内搭别闷汗" in result.broadcast_text
    assert "客户" not in result.broadcast_text
    assert "社交" not in result.broadcast_text
    assert "高温" not in result.broadcast_text


def test_recommends_outfit_handles_cool_autumn_commute_layering():
    items = [
        WardrobeItem(
            id="shirt_white",
            name="white shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="jacket_navy",
            name="navy blue jacket",
            category="outerwear",
            colors=["blue"],
            formality=2,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="pants_gray",
            name="gray trousers",
            category="bottom",
            colors=["gray"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="今天通勤上班",
        weather="北京秋天早晚有点偏凉，有风",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "早晚偏凉通勤" in result.broadcast_text
    assert "薄外层挡风" in result.broadcast_text
    assert "进室内可脱" in result.broadcast_text
    assert "内搭别太厚" in result.broadcast_text
    assert "雨天" not in result.broadcast_text
    assert "客户" not in result.broadcast_text
    assert "社交" not in result.broadcast_text


def test_recommends_outfit_handles_asr_tianliang_commute_layering():
    items = [
        WardrobeItem(
            id="shirt_white",
            name="white shirt",
            category="top",
            colors=["white"],
            formality=2,
            warmth_level=1,
            source_type="camera",
            confidence=0.9,
        ),
        WardrobeItem(
            id="jacket_navy",
            name="navy blue jacket",
            category="outerwear",
            colors=["blue"],
            formality=2,
            warmth_level=2,
            source_type="camera",
            confidence=0.9,
        ),
    ]
    request = OutfitRecommendationRequest(
        wardrobe_item_ids=[],
        occasion="今天通勤上班",
        weather="北京秋天早晚有点天凉",
    )

    result = recommend_outfit(request, wardrobe_items=items)

    assert result.broadcast_text is not None
    assert "早晚偏凉通勤" in result.broadcast_text
    assert "薄外层挡风" in result.broadcast_text
    assert "进室内可脱" in result.broadcast_text
    assert "工作场景保留一个利落锚点" not in result.broadcast_text


def test_recommends_light_family_dinner_with_conservative_safety_text():
    assets = _demo_assets()
    request = CookingRecommendationRequest(
        pantry_item_ids=["egg_1", "tomato_1", "dumpling_1"],
        people_count=3,
        time_budget_minutes=30,
        taste_tags=["light"],
        avoid_tags=["too salty"],
    )

    result = recommend_cooking(
        request,
        pantry_items=assets.pantry_items,
        preferences=assets.preferences,
    )

    assert result.domain == "cooking"
    assert result.options[0].item_ids == ["egg_1", "tomato_1", "dumpling_1"]
    assert "30 分钟" in result.options[0].summary
    assert "Fits taste target: light, less salt." in result.options[0].rationale
    assert "please confirm" in " ".join(result.options[0].safety_notes).lower()
    assert result.broadcast_text is not None
    assert "可以考虑" in result.broadcast_text
    assert "Prepare" not in result.options[0].summary
    assert "may fit dinner tonight" not in result.broadcast_text
