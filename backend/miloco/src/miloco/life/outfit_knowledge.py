# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Small outfit-advice knowledge base for speech-friendly recommendations."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class OutfitAdvice:
    """Matched outfit advice distilled for recommender output."""

    summary: str | None
    broadcast_hint: str | None
    rationale: tuple[str, ...]
    matched_rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class OutfitAdviceRule:
    id: str
    title: str
    priority: int
    occasion_keywords: tuple[str, ...] = ()
    weather_keywords: tuple[str, ...] = ()
    season_keywords: tuple[str, ...] = ()
    region_keywords: tuple[str, ...] = ()
    preference_keywords: tuple[str, ...] = ()
    rationale: tuple[str, ...] = ()
    broadcast_hint: str | None = None


OUTFIT_ADVICE_RULES: tuple[OutfitAdviceRule, ...] = (
    OutfitAdviceRule(
        id="unstable_weather_client_commute",
        title="不稳定天气客户通勤",
        priority=110,
        occasion_keywords=(
            "client",
            "meeting",
            "work",
            "office",
            "commute",
            "客户",
            "见客户",
            "开会",
            "会议",
            "办公",
            "上班",
            "通勤",
        ),
        weather_keywords=(
            "bad weather",
            "cloudy",
            "overcast",
            "天气不好",
            "阴天",
            "多云",
        ),
        rationale=(
            "天气不稳定但还没有明确下雨时，通勤见客户要预留防脏和防风余量，不直接按雨天处理。",
            "外层选轻便耐脏、进室内好整理的款式，鞋子稳一点，避免临时天气变化影响形象。",
        ),
        broadcast_hint="天气不稳定通勤见客户，选轻便耐脏外层，鞋子稳一点，进室内保持利落",
    ),
    OutfitAdviceRule(
        id="southern_humid_client_commute",
        title="南方湿热客户通勤",
        priority=112,
        occasion_keywords=(
            "client",
            "meeting",
            "work",
            "office",
            "commute",
            "客户",
            "见客户",
            "开会",
            "会议",
            "办公",
            "上班",
            "通勤",
        ),
        weather_keywords=("hot", "heat", "humid", "闷热", "潮湿", "湿热", "高温"),
        season_keywords=("summer", "夏季", "夏天"),
        region_keywords=("south", "coastal", "南方", "华南", "沿海", "广州", "深圳"),
        rationale=(
            "南方夏季湿热通勤后见客户，内搭要轻薄透气，外层负责进会议室后的利落形象。",
            "贴身层优先排汗不贴身，外套进室内再穿上，减少路上出汗影响正式感。",
        ),
        broadcast_hint="南方湿热通勤后见客户，内搭轻薄透气，不要选厚重外套，进室内用利落外层稳住形象",
    ),
    OutfitAdviceRule(
        id="humid_indoor_ac_commute",
        title="湿热通勤室内空调",
        priority=104,
        occasion_keywords=(
            "commute",
            "work",
            "office",
            "通勤",
            "上班",
            "办公",
            "办公室",
        ),
        weather_keywords=("hot", "heat", "humid", "闷热", "潮湿", "湿热", "高温"),
        season_keywords=("summer", "夏季", "夏天"),
        region_keywords=("south", "coastal", "南方", "华南", "沿海", "广州", "深圳"),
        rationale=(
            "南方夏天通勤常见外面湿热、进办公室空调偏冷，贴身层要先解决排汗和不闷。",
            "薄外层要轻便好穿脱，进室内再加上，避免路上出汗又在空调房受凉。",
        ),
        broadcast_hint="外面湿热室内空调，贴身层透气排汗，薄外层方便穿脱",
    ),
    OutfitAdviceRule(
        id="humid_commute_social_dinner",
        title="湿热通勤晚间社交",
        priority=106,
        occasion_keywords=(
            "commute",
            "work",
            "social",
            "dinner",
            "restaurant",
            "通勤",
            "上班",
            "社交",
            "吃饭",
            "朋友",
            "聚餐",
            "饭局",
            "晚上",
        ),
        weather_keywords=("hot", "heat", "humid", "闷热", "潮湿", "湿热", "高温"),
        season_keywords=("summer", "夏季", "夏天"),
        region_keywords=("south", "coastal", "南方", "华南", "沿海", "广州", "深圳"),
        rationale=(
            "南方湿热通勤后还有晚间社交，白天贴身层先解决透气排汗，晚上再用一个亮点单品提高完成度。",
            "外层或配色不要太厚重，避免通勤出汗后影响晚餐状态，同时保留干净协调的社交感。",
        ),
        broadcast_hint="湿热通勤后晚间社交，先透气排汗，晚餐保留一个亮点，其余保持干净协调",
    ),
    OutfitAdviceRule(
        id="rainy_client_meeting",
        title="雨天客户会议",
        priority=108,
        occasion_keywords=(
            "client",
            "meeting",
            "work",
            "office",
            "客户",
            "见客户",
            "开会",
            "会议",
            "办公",
            "上班",
        ),
        weather_keywords=("rain", "rainy", "shower", "drizzle", "有雨", "下雨", "雨天"),
        rationale=(
            "雨天见客户或开会要把防滑耐脏和上半身利落同时处理好。",
            "外层尽量选进室内可脱换的款式，避免淋雨后影响会议形象。",
        ),
        broadcast_hint="雨天见客户或开会，鞋履防滑耐脏，上半身保持利落",
    ),
    OutfitAdviceRule(
        id="rainy_sport_outing",
        title="雨天运动出行",
        priority=102,
        occasion_keywords=(
            "sport",
            "soccer",
            "football",
            "running",
            "gym",
            "运动",
            "踢足球",
            "足球",
            "跑步",
            "健身",
        ),
        weather_keywords=("rain", "rainy", "shower", "drizzle", "有雨", "下雨", "雨天"),
        rationale=(
            "雨天或雨后运动要先处理鞋底抓地、防滑和衣物快干，避免只按普通运动场景给建议。",
            "上衣优先排汗快干，必要时带一件备用上衣，运动后不要穿着湿衣服久待。",
        ),
        broadcast_hint="雨天运动出行，鞋底抓地防滑，上衣快干透气，运动后准备备用上衣",
    ),
    OutfitAdviceRule(
        id="jiangnan_plum_rain_cool_commute",
        title="江南梅雨湿冷通勤",
        priority=101,
        occasion_keywords=("commute", "work", "office", "上班", "通勤", "办公"),
        weather_keywords=(
            "plum rain",
            "wet cold",
            "rain",
            "rainy",
            "drizzle",
            "梅雨",
            "湿冷",
            "阴雨",
            "潮湿",
            "有雨",
            "下雨",
        ),
        region_keywords=("jiangnan", "shanghai", "江南", "上海", "杭州", "苏州"),
        rationale=(
            "江南梅雨季通勤容易同时遇到路面湿滑、空气潮湿和体感偏冷，不能只按普通雨天或普通偏凉处理。",
            "外层优先防风防潮，鞋底要防滑，内搭保持透气不闷汗，进办公室后也更容易维持干爽。",
        ),
        broadcast_hint="江南梅雨湿冷通勤，外层防风防潮，鞋底防滑，内搭别闷汗",
    ),
    OutfitAdviceRule(
        id="rainy_commute",
        title="雨天通勤",
        priority=95,
        occasion_keywords=("commute", "work", "office", "上班", "通勤", "办公"),
        weather_keywords=("rain", "rainy", "shower", "drizzle", "有雨", "下雨", "雨天"),
        rationale=(
            "雨天通勤优先耐脏、快干和防滑，减少拖地裤脚与怕水材质。",
            "外层最好可脱换，进室内后不影响整体整洁度。",
        ),
        broadcast_hint="雨天通勤重点放在防滑、耐脏和可脱换外层",
    ),
    OutfitAdviceRule(
        id="hot_humid_day",
        title="高温湿热",
        priority=90,
        weather_keywords=(
            "hot",
            "heat",
            "humid",
            "warm",
            "高温",
            "炎热",
            "闷热",
            "潮湿",
            "湿热",
        ),
        season_keywords=("summer", "夏季", "夏天"),
        region_keywords=("south", "coastal", "南方", "华南", "沿海", "广州", "深圳"),
        rationale=(
            "高温或湿热天气优先轻薄、透气、排汗材质，版型不要过紧。",
            "浅色和留有空气感的搭配更适合白天出行，室内空调环境可备薄外层。",
        ),
        broadcast_hint="高温天气优先轻薄透气，室内空调可以备一件薄外层",
    ),
    OutfitAdviceRule(
        id="cool_autumn_commute_layering",
        title="早晚偏凉通勤",
        priority=100,
        occasion_keywords=("commute", "work", "office", "通勤", "上班", "办公"),
        weather_keywords=(
            "cool",
            "cold",
            "wind",
            "windy",
            "偏凉",
            "天凉",
            "有点凉",
            "降温",
            "冷",
            "有风",
            "大风",
        ),
        season_keywords=("autumn", "fall", "秋天", "秋季"),
        region_keywords=("north", "beijing", "北方", "华北", "北京"),
        rationale=(
            "秋季或北方通勤常见早晚偏凉、室内外温差，重点不是加厚，而是薄外层挡风并方便穿脱。",
            "内搭不要太厚，避免路上保暖够了但进地铁、办公室后闷热；外层进室内可脱，整体更利落。",
        ),
        broadcast_hint="早晚偏凉通勤，薄外层挡风，进室内可脱，内搭别太厚",
    ),
    OutfitAdviceRule(
        id="cool_layering",
        title="偏凉分层",
        priority=84,
        weather_keywords=(
            "cool",
            "cold",
            "wind",
            "windy",
            "cloudy",
            "偏凉",
            "天凉",
            "有点凉",
            "降温",
            "冷",
            "大风",
        ),
        season_keywords=("autumn", "winter", "fall", "秋季", "冬季"),
        rationale=(
            "偏凉或大风天气适合内搭、保暖中层和防风外层的分层思路。",
            "分层搭配便于在室内外温差变化时快速调整。",
        ),
        broadcast_hint="偏凉天气用分层搭配，外层负责挡风，进室内再脱",
    ),
    OutfitAdviceRule(
        id="work_meeting_polish",
        title="工作会议",
        priority=80,
        occasion_keywords=(
            "work",
            "office",
            "meeting",
            "client",
            "interview",
            "上班",
            "办公",
            "会议",
            "客户",
            "面试",
        ),
        rationale=(
            "工作场景需要有一个利落锚点，比如衬衫、西装外套、挺括长裤或干净鞋履。",
            "整体颜色保持克制，允许用一个低调配饰增加个人感。",
        ),
        broadcast_hint="工作场景保留一个利落锚点，颜色别太跳",
    ),
    OutfitAdviceRule(
        id="social_evening_balance",
        title="社交晚间",
        priority=76,
        occasion_keywords=(
            "social",
            "dinner",
            "date",
            "party",
            "restaurant",
            "drinks",
            "社交",
            "聚会",
            "约会",
            "晚餐",
            "吃饭",
            "朋友",
            "聚餐",
            "饭局",
            "今晚",
            "晚上",
        ),
        rationale=(
            "社交场景可以采用一个亮点单品加基础色压住整体的思路。",
            "鞋子和包最好兼顾舒适与精致，避免只好看但走路不舒服。",
        ),
        broadcast_hint="社交场景可以有一个亮点单品，其余保持干净协调",
    ),
    OutfitAdviceRule(
        id="sport_mobility",
        title="运动出行",
        priority=92,
        occasion_keywords=(
            "sport",
            "soccer",
            "football",
            "running",
            "gym",
            "运动",
            "踢足球",
            "足球",
            "跑步",
            "健身",
        ),
        rationale=(
            "运动场景优先排汗、活动空间和鞋底抓地力，不建议选择限制动作的单品。",
            "如果运动后还有社交安排，可以准备干净外层或替换上衣。",
        ),
        broadcast_hint="运动场景优先排汗和活动空间，鞋子要稳",
    ),
    OutfitAdviceRule(
        id="video_call_upper_body",
        title="视频沟通",
        priority=70,
        occasion_keywords=("video", "call", "meeting", "直播", "视频", "线上", "远程"),
        weather_keywords=("indoor", "室内"),
        rationale=(
            "视频场景更关注上半身，领口、肩线和颜色对镜头效果影响更明显。",
            "避免过密小图案，选择和背景有区分度的颜色更稳妥。",
        ),
        broadcast_hint="视频场景重点看上半身，颜色要和背景拉开一点",
    ),
    OutfitAdviceRule(
        id="travel_day",
        title="旅行移动",
        priority=68,
        occasion_keywords=(
            "travel",
            "trip",
            "airport",
            "train",
            "旅行",
            "出差",
            "机场",
            "高铁",
        ),
        rationale=(
            "长时间移动要优先舒适、耐皱和口袋/包容量，减少难打理材质。",
            "外层和鞋履最好适应步行、候车和室内空调的切换。",
        ),
        broadcast_hint="旅行出行优先舒适耐皱，鞋子和外层要适合长时间移动",
    ),
)


def build_outfit_style_advice(
    *,
    occasion: str,
    weather: str | None,
    preference_tags: list[str] | tuple[str, ...] | None = None,
) -> OutfitAdvice:
    """Match weather, season, region, and occasion rules into compact advice."""
    context = _normalize_context(
        " ".join([occasion, weather or "", " ".join(preference_tags or [])])
    )
    scored_rules: list[tuple[int, OutfitAdviceRule]] = []
    for rule in OUTFIT_ADVICE_RULES:
        score = _rule_score(rule, context)
        if score > 0:
            scored_rules.append((score, rule))

    scored_rules.sort(key=lambda item: (item[0], item[1].priority), reverse=True)
    selected_rules = [rule for _, rule in scored_rules[:3]]
    if not selected_rules:
        return OutfitAdvice(
            summary=None,
            broadcast_hint=None,
            rationale=(),
            matched_rule_ids=(),
        )

    rationale = _unique_points(
        point for rule in selected_rules for point in rule.rationale
    )[:5]
    return OutfitAdvice(
        summary="、".join(rule.title for rule in selected_rules),
        broadcast_hint=selected_rules[0].broadcast_hint,
        rationale=tuple(rationale),
        matched_rule_ids=tuple(rule.id for rule in selected_rules),
    )


def _rule_score(rule: OutfitAdviceRule, context: str) -> int:
    if (
        rule.id == "unstable_weather_client_commute"
        and not _unstable_weather_client_commute_context(context)
    ):
        return 0
    if (
        rule.id == "southern_humid_client_commute"
        and not _southern_humid_client_commute_context(context)
    ):
        return 0
    if rule.id == "humid_indoor_ac_commute" and not _humid_indoor_ac_commute_context(
        context
    ):
        return 0
    if (
        rule.id == "humid_commute_social_dinner"
        and not _humid_commute_social_dinner_context(context)
    ):
        return 0
    if rule.id == "rainy_client_meeting" and not _rainy_client_meeting_context(context):
        return 0
    if rule.id == "rainy_sport_outing" and not _rainy_sport_outing_context(context):
        return 0
    if (
        rule.id == "jiangnan_plum_rain_cool_commute"
        and not _jiangnan_plum_rain_cool_commute_context(context)
    ):
        return 0
    if rule.id == "rainy_commute" and not _rainy_commute_context(context):
        return 0
    if (
        rule.id == "cool_autumn_commute_layering"
        and not _cool_autumn_commute_layering_context(context)
    ):
        return 0
    score = 0
    score += 5 if _has_any(context, rule.occasion_keywords) else 0
    score += 5 if _has_any(context, rule.weather_keywords) else 0
    score += 3 if _has_any(context, rule.season_keywords) else 0
    score += 2 if _has_any(context, rule.region_keywords) else 0
    score += 2 if _has_any(context, rule.preference_keywords) else 0
    if score == 0:
        return 0
    if rule.id == "social_evening_balance" and _social_dinner_context(context):
        score += 20
    if rule.id == "video_call_upper_body" and _video_meeting_context(context):
        score += 20
    return score + rule.priority


def _rainy_client_meeting_context(context: str) -> bool:
    client_meeting_terms = (
        "client",
        "meeting",
        "客户",
        "见客户",
        "开会",
        "会议",
    )
    rain_terms = ("rain", "rainy", "shower", "drizzle", "有雨", "下雨", "雨天")
    return _has_any(context, client_meeting_terms) and _has_any(context, rain_terms)


def _rainy_commute_context(context: str) -> bool:
    commute_terms = ("commute", "work", "office", "上班", "通勤", "办公")
    rain_terms = ("rain", "rainy", "shower", "drizzle", "有雨", "下雨", "雨天")
    return _has_any(context, commute_terms) and _has_any(context, rain_terms)


def _rainy_sport_outing_context(context: str) -> bool:
    sport_terms = (
        "sport",
        "soccer",
        "football",
        "running",
        "gym",
        "运动",
        "踢足球",
        "足球",
        "跑步",
        "健身",
    )
    rain_terms = ("rain", "rainy", "shower", "drizzle", "有雨", "下雨", "雨天")
    return _has_any(context, sport_terms) and _has_any(context, rain_terms)


def _jiangnan_plum_rain_cool_commute_context(context: str) -> bool:
    commute_terms = ("commute", "work", "office", "通勤", "上班", "办公")
    region_terms = ("jiangnan", "shanghai", "江南", "上海", "杭州", "苏州")
    wet_cool_terms = (
        "plum rain",
        "wet cold",
        "rain",
        "rainy",
        "drizzle",
        "梅雨",
        "湿冷",
        "阴雨",
        "潮湿",
        "有雨",
        "下雨",
    )
    return (
        _has_any(context, commute_terms)
        and _has_any(context, region_terms)
        and _has_any(context, wet_cool_terms)
    )


def _cool_autumn_commute_layering_context(context: str) -> bool:
    commute_terms = ("commute", "work", "office", "通勤", "上班", "办公")
    cool_terms = (
        "cool",
        "cold",
        "wind",
        "windy",
        "偏凉",
        "天凉",
        "有点凉",
        "降温",
        "冷",
        "有风",
        "大风",
    )
    autumn_terms = ("autumn", "fall", "秋天", "秋季")
    north_terms = ("north", "beijing", "北方", "华北", "北京")
    return (
        _has_any(context, commute_terms)
        and _has_any(context, cool_terms)
        and (_has_any(context, autumn_terms) or _has_any(context, north_terms))
    )


def _unstable_weather_client_commute_context(context: str) -> bool:
    client_meeting_terms = (
        "client",
        "meeting",
        "客户",
        "见客户",
        "开会",
        "会议",
    )
    commute_terms = ("commute", "通勤", "上班")
    vague_weather_terms = (
        "bad weather",
        "cloudy",
        "overcast",
        "天气不好",
        "阴天",
        "多云",
    )
    rain_terms = ("rain", "rainy", "shower", "drizzle", "有雨", "下雨", "雨天")
    return (
        _has_any(context, client_meeting_terms)
        and _has_any(context, commute_terms)
        and _has_any(context, vague_weather_terms)
        and not _has_any(context, rain_terms)
    )


def _southern_humid_client_commute_context(context: str) -> bool:
    client_meeting_terms = (
        "client",
        "meeting",
        "客户",
        "见客户",
        "开会",
        "会议",
    )
    commute_terms = ("commute", "通勤", "上班")
    hot_humid_terms = ("hot", "heat", "humid", "高温", "闷热", "潮湿", "湿热")
    south_summer_terms = (
        "summer",
        "south",
        "coastal",
        "夏季",
        "夏天",
        "南方",
        "华南",
        "沿海",
        "广州",
        "深圳",
    )
    return (
        _has_any(context, client_meeting_terms)
        and _has_any(context, commute_terms)
        and _has_any(context, hot_humid_terms)
        and _has_any(context, south_summer_terms)
    )


def _humid_indoor_ac_commute_context(context: str) -> bool:
    commute_terms = ("commute", "work", "office", "通勤", "上班", "办公", "办公室")
    hot_humid_terms = ("hot", "heat", "humid", "高温", "闷热", "潮湿", "湿热")
    south_summer_terms = (
        "summer",
        "south",
        "coastal",
        "夏季",
        "夏天",
        "南方",
        "华南",
        "沿海",
        "广州",
        "深圳",
    )
    indoor_ac_terms = ("indoor", "air conditioning", "ac", "室内", "空调", "办公室")
    return (
        _has_any(context, commute_terms)
        and _has_any(context, hot_humid_terms)
        and _has_any(context, south_summer_terms)
        and _has_any(context, indoor_ac_terms)
    )


def _humid_commute_social_dinner_context(context: str) -> bool:
    commute_terms = ("commute", "work", "通勤", "上班")
    social_terms = (
        "social",
        "dinner",
        "restaurant",
        "朋友",
        "社交",
        "聚餐",
        "饭局",
        "吃饭",
        "晚上",
    )
    hot_humid_terms = ("hot", "heat", "humid", "高温", "闷热", "潮湿", "湿热")
    south_summer_terms = (
        "summer",
        "south",
        "coastal",
        "夏季",
        "夏天",
        "南方",
        "华南",
        "沿海",
        "广州",
        "深圳",
    )
    client_meeting_terms = ("client", "meeting", "客户", "见客户", "开会", "会议")
    return (
        _has_any(context, commute_terms)
        and _has_any(context, social_terms)
        and _has_any(context, hot_humid_terms)
        and _has_any(context, south_summer_terms)
        and not _has_any(context, client_meeting_terms)
    )


def _social_dinner_context(context: str) -> bool:
    social_terms = ("朋友", "社交", "聚会", "聚餐", "饭局", "约会")
    dinner_terms = ("吃饭", "晚餐", "今晚", "晚上", "dinner", "restaurant")
    return _has_any(context, social_terms) and _has_any(context, dinner_terms)


def _video_meeting_context(context: str) -> bool:
    video_terms = ("视频", "线上", "远程", "video", "call")
    meeting_terms = ("会议", "沟通", "办公", "meeting", "work")
    return _has_any(context, video_terms) and _has_any(context, meeting_terms)


def _has_any(context: str, keywords: tuple[str, ...]) -> bool:
    if not keywords:
        return False
    return any(_normalize_context(keyword).strip() in context for keyword in keywords)


def _normalize_context(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[\s,_/\\\-]+", " ", text)
    return f" {text.strip()} "


def _unique_points(points: Iterable[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for point in points:
        if not isinstance(point, str):
            continue
        normalized = point.strip()
        if not normalized or normalized in seen:
            continue
        unique.append(normalized)
        seen.add(normalized)
    return unique
