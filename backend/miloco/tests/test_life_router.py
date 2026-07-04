# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""FastAPI seam tests for the life-domain hackathon demo."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from miloco.life.extractor import LifeExtractionResult
from miloco.life.router import router
from miloco.life.schema import WardrobeItem
from miloco.life.voice_session import clear_life_voice_sessions

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "life_mimo_mock.json"
OUTFIT_COMMAND = "\u5e2e\u6211\u770b\u770b\u8fd9\u4ef6\u8863\u670d\u600e\u4e48\u642d"
OUTFIT_FOLLOWUP = "\u8fd8\u6709\u522b\u7684\u5efa\u8bae\u5417"
OUTFIT_VISIBLE_FOLLOWUP = "\u6211\u6362\u4e86\u4e00\u4ef6\uff0c\u4f60\u518d\u770b\u770b"
UNRELATED_COMMAND = "\u4eca\u5929\u5929\u6c14\u600e\u4e48\u6837"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def _fixture_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_life_demo_endpoint_chains_mock_mimo_to_recommendations():
    response = _client().post(
        "/api/life/demo",
        json={"mimo_payload": _fixture_payload()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["source_id"] == "demo_afternoon_interview_dinner"
    assert data["outfit"]["title"] == "深灰色西装外套、白色衬衫"
    assert data["cooking"]["title"] == "番茄鸡蛋配速冻饺子"
    assert "请先确认锅具状态和食材新鲜度" in data["cooking_broadcast_text"]
    assert data["low_confidence_notes"]


def test_life_demo_endpoint_can_persist_assets_and_history(tmp_path):
    db_path = tmp_path / "life-demo.db"

    response = _client().post(
        "/api/life/demo",
        json={
            "mimo_payload": _fixture_payload(),
            "persist": True,
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["persistence"] == {
        "source_id": "demo_afternoon_interview_dinner",
        "wardrobe_count": 2,
        "pantry_count": 3,
        "preference_count": 2,
        "recommendation_history_count": 2,
    }
    assert db_path.exists()

    from miloco.life.repo import LifeRepo

    history = LifeRepo(db_path).list_recommendation_history()
    assert len(LifeRepo(db_path).list_wardrobe_items()) == 2
    assert len(LifeRepo(db_path).list_pantry_items()) == 3
    assert {item["domain"] for item in history} == {"outfit", "cooking"}
    assert any(
        "请先确认锅具状态和食材新鲜度" in item["broadcast_text"] for item in history
    )


def test_life_history_endpoint_reads_persisted_recommendations(tmp_path):
    db_path = tmp_path / "life-demo.db"
    client = _client()
    client.post(
        "/api/life/demo",
        json={
            "mimo_payload": _fixture_payload(),
            "persist": True,
            "db_path": str(db_path),
        },
    )

    response = client.get(
        "/api/life/history",
        params={"db_path": str(db_path), "domain": "cooking", "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["db_path"] == str(db_path)
    assert body["data"]["count"] == 1
    assert body["data"]["history"][0]["domain"] == "cooking"
    assert body["data"]["history"][0]["source_id"] == "demo_afternoon_interview_dinner"
    assert body["data"]["history"][0]["option_titles"] == ["番茄鸡蛋配速冻饺子"]
    assert (
        "请先确认锅具状态和食材新鲜度" in body["data"]["history"][0]["broadcast_text"]
    )


def test_life_history_endpoint_can_filter_by_source_id(tmp_path):
    db_path = tmp_path / "life-demo.db"
    client = _client()
    client.post(
        "/api/life/demo",
        json={
            "mimo_payload": _fixture_payload(),
            "persist": True,
            "db_path": str(db_path),
        },
    )

    response = client.get(
        "/api/life/history",
        params={
            "db_path": str(db_path),
            "source_id": "demo_afternoon_interview_dinner",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["source_id"] == "demo_afternoon_interview_dinner"
    assert body["data"]["count"] == 2
    assert {item["source_id"] for item in body["data"]["history"]} == {
        "demo_afternoon_interview_dinner"
    }


def test_life_history_endpoint_returns_recording_hint_for_empty_db(tmp_path):
    db_path = tmp_path / "life-demo.db"

    response = _client().get(
        "/api/life/history",
        params={"db_path": str(db_path), "domain": "cooking"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"] == {
        "db_path": str(db_path),
        "domain": "cooking",
        "count": 0,
        "history": [],
        "history_hint": (
            "No cooking recommendation history yet. Run the life demo with "
            "--persist before recording the history step."
        ),
    }


def test_life_trigger_schedule_outfit_uses_inventory_without_camera(tmp_path):
    db_path = tmp_path / "life-trigger.db"
    client = _client()
    client.post(
        "/api/life/demo",
        json={
            "mimo_payload": _fixture_payload(),
            "persist": True,
            "db_path": str(db_path),
        },
    )

    response = client.post(
        "/api/life/trigger",
        json={
            "trigger_source": "schedule",
            "domain": "outfit",
            "occasion": "morning commute",
            "weather": "cool rainy morning",
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["trigger_source"] == "schedule"
    assert data["domain"] == "outfit"
    assert data["used_visual_input"] is False
    assert data["camera_required"] is False
    assert data["outfit"]["title"] == "深灰色西装外套、白色衬衫"
    assert data["cooking"] is None
    assert data["history"]["source_id"] == "schedule:outfit"


def test_life_trigger_inventory_outfit_speaks_one_set_not_all_clothes(tmp_path):
    from miloco.life.repo import LifeRepo

    db_path = tmp_path / "life-trigger-inventory-set.db"
    repo = LifeRepo(db_path)
    repo.save_extraction_result(
        LifeExtractionResult(
            source_id="inventory_set_fixture",
            caption="wardrobe with multiple alternatives",
            wardrobe_items=[
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
            ],
            pantry_items=[],
            preferences=[],
        )
    )

    response = _client().post(
        "/api/life/trigger",
        json={
            "trigger_source": "voice_intent",
            "domain": "outfit",
            "occasion": "today outing",
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["outfit"]["title"] == "蓝色运动外套、白色格纹衬衫、浅灰色长裤"
    assert "绿色外套" not in data["outfit_broadcast_text"]
    assert "绿色衬衫" not in data["outfit_broadcast_text"]


def test_life_trigger_schedule_outfit_empty_inventory_avoids_camera(tmp_path):
    db_path = tmp_path / "life-trigger-empty.db"

    response = _client().post(
        "/api/life/trigger",
        json={
            "trigger_source": "schedule",
            "domain": "outfit",
            "occasion": "08:30 outfit reminder",
            "weather": "warm sunny morning",
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["used_visual_input"] is False
    assert data["camera_required"] is False
    assert data["outfit"] is None
    assert data["history"] is None
    assert data["low_confidence_notes"] == [
        "No stored wardrobe items are available; ask the user before capturing a camera clip."
    ]


def test_life_trigger_voice_intent_can_use_supplied_mimo_payload(tmp_path):
    db_path = tmp_path / "life-trigger-voice.db"

    response = _client().post(
        "/api/life/trigger",
        json={
            "trigger_source": "voice_intent",
            "domain": "outfit",
            "source_id": "voice_check_this_shirt",
            "mimo_payload": {
                "source_id": "voice_check_this_shirt",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "white shirt",
                        "category": "top",
                        "colors": ["white"],
                        "formality": 3,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    }
                ],
                "pantry": [],
                "preferences": [],
            },
            "occasion": "video meeting",
            "weather": "indoor",
            "persist": True,
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["trigger_source"] == "voice_intent"
    assert data["used_visual_input"] is True
    assert data["camera_required"] is True
    assert data["outfit"]["title"] == "白色衬衫"
    assert data["history"]["source_id"] == "voice_check_this_shirt"


async def test_life_trigger_rejects_concurrent_live_mimo_visual_request(
    monkeypatch,
    tmp_path,
):
    from miloco.life.service import run_life_trigger

    first_mimo_started = asyncio.Event()
    release_first_mimo = asyncio.Event()
    mimo_calls = 0

    async def fake_extract_life_assets_with_live_mimo(*, observation):
        nonlocal mimo_calls
        mimo_calls += 1
        if mimo_calls == 1:
            first_mimo_started.set()
            await release_first_mimo.wait()
        return (
            LifeExtractionResult(
                source_id=observation.source_id,
                caption="fake live extraction",
                wardrobe_items=[
                    WardrobeItem(
                        id="w_001",
                        name="white shirt",
                        category="top",
                        colors=["white"],
                        formality=3,
                        warmth_level=1,
                        source_type="camera",
                        confidence=0.9,
                    )
                ],
                pantry_items=[],
                preferences=[],
                low_confidence_notes=[],
            ),
            "{}",
        )

    monkeypatch.setattr(
        "miloco.life.service.extract_life_assets_with_live_mimo",
        fake_extract_life_assets_with_live_mimo,
    )

    async def run_visual_trigger(source_id: str):
        return await run_life_trigger(
            SimpleNamespace(
                trigger_source="voice_intent",
                domain="outfit",
                source_id=source_id,
                prompt="focus on visible clothing",
                clip_base64="ZmFrZSBtcDQ=",
                mimo_payload=None,
                occasion="video meeting",
                weather="indoor",
                people_count=1,
                time_budget_minutes=30,
                persist=False,
                db_path=str(tmp_path / f"{source_id}.db"),
            )
        )

    first_task = asyncio.create_task(run_visual_trigger("first_visual_request"))
    await asyncio.wait_for(first_mimo_started.wait(), timeout=1)

    second = await run_visual_trigger("second_visual_request")
    release_first_mimo.set()
    first = await first_task

    assert first["outfit"]["title"] == "白色衬衫"
    assert second["reason"] == "mimo_lease_busy"
    assert second["outfit"] is None
    assert second["outfit_broadcast_text"] == "视觉理解正在处理上一条请求，请稍后再试。"
    assert second["low_confidence_notes"] == [
        "视觉理解正在处理上一条请求，请稍后再试。"
    ]
    assert second["mimo_lease"] == {
        "resource_type": "mimo",
        "resource_id": "visual",
        "acquired": False,
        "lease_released": True,
        "release_reason": "busy",
    }
    assert mimo_calls == 1


def test_life_trigger_cooking_requires_inventory_or_visual_input(tmp_path):
    db_path = tmp_path / "life-trigger-cooking-empty.db"

    response = _client().post(
        "/api/life/trigger",
        json={
            "trigger_source": "voice_intent",
            "domain": "cooking",
            "people_count": 2,
            "time_budget_minutes": 20,
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["used_visual_input"] is False
    assert data["camera_required"] is False
    assert data["cooking"] is None
    assert data["low_confidence_notes"] == [
        "No stored pantry items are available; ask the user before capturing a fridge or kitchen clip."
    ]


def test_life_trigger_accepts_voice_command_text_without_domain(tmp_path):
    db_path = tmp_path / "life-trigger-command-text.db"

    response = _client().post(
        "/api/life/trigger",
        json={
            "trigger_source": "voice_intent",
            "text": "帮我看看这件衣服怎么搭",
            "occasion": "video meeting",
            "weather": "indoor",
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["matched"] is True
    assert data["domain"] == "outfit"
    assert data["action"] == "needs_visual_capture"
    assert data["camera_required"] is True
    assert data["needs_visual_capture"] is True
    assert data["trigger"] is None


def test_life_text_trigger_ignores_unrelated_command_without_camera(tmp_path):
    db_path = tmp_path / "life-text-trigger.db"

    response = _client().post(
        "/api/life/text-trigger",
        json={
            "text": "打开客厅灯",
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["matched"] is False
    assert data["action"] == "ignored"
    assert data["camera_required"] is False
    assert data["needs_visual_capture"] is False
    assert data["trigger"] is None


def test_life_text_trigger_outfit_command_requests_short_capture(tmp_path):
    db_path = tmp_path / "life-text-trigger-outfit.db"

    response = _client().post(
        "/api/life/text-trigger",
        json={
            "text": "帮我看看这件衣服怎么搭",
            "occasion": "video meeting",
            "weather": "indoor",
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["matched"] is True
    assert data["domain"] == "outfit"
    assert data["action"] == "needs_visual_capture"
    assert data["camera_required"] is True
    assert data["needs_visual_capture"] is True
    assert data["trigger"] is None
    assert "visible clothing" in data["prompt"]


def test_life_text_trigger_outfit_command_with_mimo_payload_runs_trigger(tmp_path):
    db_path = tmp_path / "life-text-trigger-voice.db"

    response = _client().post(
        "/api/life/text-trigger",
        json={
            "text": "帮我看看这件衣服怎么搭",
            "source_id": "voice_check_this_shirt",
            "mimo_payload": {
                "source_id": "voice_check_this_shirt",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "white shirt",
                        "category": "top",
                        "colors": ["white"],
                        "formality": 3,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    }
                ],
                "pantry": [],
                "preferences": [],
            },
            "occasion": "video meeting",
            "weather": "indoor",
            "persist": True,
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["matched"] is True
    assert data["domain"] == "outfit"
    assert data["action"] == "triggered"
    assert data["camera_required"] is True
    assert data["needs_visual_capture"] is False
    assert data["trigger"]["trigger_source"] == "voice_intent"
    assert data["trigger"]["used_visual_input"] is True
    assert data["trigger"]["outfit"]["title"] == "白色衬衫"
    assert data["trigger"]["history"]["source_id"] == "voice_check_this_shirt"


def test_life_voice_command_starts_session_and_requests_camera_clip(tmp_path):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command.db"

    response = _client().post(
        "/api/life/voice-command",
        json={
            "text": OUTFIT_COMMAND,
            "camera_id": "1182348802",
            "speaker_id": "xiaomi_speaker_01",
            "occasion": "video meeting",
            "weather": "indoor",
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["matched"] is True
    assert data["domain"] == "outfit"
    assert data["session_active"] is True
    assert data["session_id"]
    assert data["action"] == "awaiting_visual_capture"
    assert data["needs_visual_capture"] is True
    assert data["camera_request"] == {
        "camera_id": "1182348802",
        "channel": 0,
        "duration_ms": 2000,
        "reason": "visible_object_reference",
        "submit_endpoint": "/api/life/voice-command",
        "session_id": data["session_id"],
    }
    assert data["speaker_request"] is None


def test_life_voice_command_responds_with_speaker_request_when_visual_is_supplied(
    tmp_path,
):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-visual.db"

    response = _client().post(
        "/api/life/voice-command",
        json={
            "text": OUTFIT_COMMAND,
            "speaker_id": "xiaomi_speaker_01",
            "mimo_payload": {
                "source_id": "voice_check_this_shirt",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "white shirt",
                        "category": "top",
                        "colors": ["white"],
                        "formality": 3,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    }
                ],
                "pantry": [],
                "preferences": [],
            },
            "occasion": "video meeting",
            "weather": "indoor",
            "persist": True,
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["matched"] is True
    assert data["domain"] == "outfit"
    assert data["action"] == "responded"
    assert data["needs_visual_capture"] is False
    assert data["camera_request"] is None
    assert data["trigger"]["outfit"]["title"] == "白色衬衫"
    assert data["broadcast_text"]
    assert data["speaker_request"] == {
        "channel": "xiaomi_speaker",
        "preferred_device_id": "xiaomi_speaker_01",
        "message": data["broadcast_text"],
        "requires_ack": False,
    }
    assert "穿搭建议" in data["speaker_request"]["message"]
    assert "For " not in data["speaker_request"]["message"]
    assert "try " not in data["speaker_request"]["message"]


def test_life_voice_command_infers_weather_and_occasion_from_text_when_visual_supplied(
    tmp_path,
):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-text-context.db"

    response = _client().post(
        "/api/life/voice-command",
        json={
            "text": "今天下雨天通勤上班，帮我看看这些衣服怎么搭",
            "speaker_id": "xiaomi_speaker_01",
            "mimo_payload": {
                "source_id": "voice_rainy_commute",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "white shirt",
                        "category": "top",
                        "colors": ["white"],
                        "formality": 3,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    }
                ],
                "pantry": [],
                "preferences": [],
            },
            "persist": True,
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["matched"] is True
    assert data["domain"] == "outfit"
    assert data["action"] == "responded"
    assert "今天上班通勤" in data["broadcast_text"]
    assert "防滑、耐脏和可脱换外层" in data["broadcast_text"]
    assert "rainy" not in data["broadcast_text"].lower()


def test_life_voice_command_keeps_inferred_context_after_visual_capture(tmp_path):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-two-step-context.db"
    client = _client()

    first = client.post(
        "/api/life/voice-command",
        json={
            "text": "今天下雨天通勤上班，帮我看看这些衣服怎么搭",
            "camera_id": "1182348802",
            "speaker_id": "xiaomi_speaker_01",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": "今天下雨天通勤上班，帮我看看这些衣服怎么搭",
            "session_id": first["session_id"],
            "speaker_id": "xiaomi_speaker_01",
            "mimo_payload": {
                "source_id": "voice_rainy_commute_clip",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "white shirt",
                        "category": "top",
                        "colors": ["white"],
                        "formality": 3,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    }
                ],
                "pantry": [],
                "preferences": [],
            },
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["action"] == "responded"
    assert "今天上班通勤" in data["broadcast_text"]
    assert "防滑、耐脏和可脱换外层" in data["broadcast_text"]


def test_life_voice_command_infers_video_meeting_after_visual_capture(tmp_path):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-video-meeting-context.db"
    client = _client()

    first = client.post(
        "/api/life/voice-command",
        json={
            "text": "下午要开视频会议，办公室空调有点冷，帮我看看这些衣服怎么搭",
            "camera_id": "1182348802",
            "speaker_id": "xiaomi_speaker_01",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": "下午要开视频会议，办公室空调有点冷，帮我看看这些衣服怎么搭",
            "session_id": first["session_id"],
            "speaker_id": "xiaomi_speaker_01",
            "mimo_payload": {
                "source_id": "voice_video_meeting_clip",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "white shirt",
                        "category": "top",
                        "colors": ["white"],
                        "formality": 3,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_002",
                        "name": "navy blue jacket",
                        "category": "outerwear",
                        "colors": ["blue"],
                        "formality": 2,
                        "warmth_level": 2,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                ],
                "pantry": [],
                "preferences": [],
            },
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["action"] == "responded"
    assert "下午视频会议" in data["broadcast_text"]
    assert "视频场景重点看上半身" in data["broadcast_text"]
    assert "颜色要和背景拉开一点" in data["broadcast_text"]
    assert "工作场景保留一个利落锚点" not in data["broadcast_text"]


def test_life_voice_command_infers_rainy_client_meeting_after_visual_capture(
    tmp_path,
):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-rainy-client-meeting-context.db"
    client = _client()

    first = client.post(
        "/api/life/voice-command",
        json={
            "text": "今天下雨还要见客户开会，帮我看看这些衣服怎么搭",
            "camera_id": "1182348802",
            "speaker_id": "xiaomi_speaker_01",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": "今天下雨还要见客户开会，帮我看看这些衣服怎么搭",
            "session_id": first["session_id"],
            "speaker_id": "xiaomi_speaker_01",
            "mimo_payload": {
                "source_id": "voice_rainy_client_meeting_clip",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "white shirt",
                        "category": "top",
                        "colors": ["white"],
                        "formality": 3,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_002",
                        "name": "navy blue jacket",
                        "category": "outerwear",
                        "colors": ["blue"],
                        "formality": 2,
                        "warmth_level": 2,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                ],
                "pantry": [],
                "preferences": [],
            },
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["action"] == "responded"
    assert "今天见客户开会" in data["broadcast_text"]
    assert "雨天见客户或开会" in data["broadcast_text"]
    assert "鞋履防滑耐脏" in data["broadcast_text"]
    assert "上半身保持利落" in data["broadcast_text"]
    assert "社交场景" not in data["broadcast_text"]


def test_life_voice_command_infers_southern_humid_client_commute_after_visual_capture(
    tmp_path,
):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-southern-humid-client-context.db"
    client = _client()

    text = "南方夏天通勤有点闷热，等下还要见客户开会，帮我看看这些衣服怎么搭"
    first = client.post(
        "/api/life/voice-command",
        json={
            "text": text,
            "camera_id": "1182348802",
            "speaker_id": "xiaomi_speaker_01",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": text,
            "session_id": first["session_id"],
            "speaker_id": "xiaomi_speaker_01",
            "mimo_payload": {
                "source_id": "voice_southern_humid_client_commute_clip",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "white shirt",
                        "category": "top",
                        "colors": ["white"],
                        "formality": 3,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_002",
                        "name": "navy blue jacket",
                        "category": "outerwear",
                        "colors": ["blue"],
                        "formality": 2,
                        "warmth_level": 2,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                ],
                "pantry": [],
                "preferences": [],
            },
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["action"] == "responded"
    assert "今天通勤后见客户开会" in data["broadcast_text"]
    assert "南方湿热通勤后见客户" in data["broadcast_text"]
    assert "内搭轻薄透气" in data["broadcast_text"]
    assert "利落外层稳住形象" in data["broadcast_text"]
    assert "雨天见客户" not in data["broadcast_text"]
    assert "社交场景" not in data["broadcast_text"]


def test_life_voice_command_infers_vague_bad_weather_client_commute_after_visual_capture(
    tmp_path,
):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-bad-weather-client-context.db"
    client = _client()

    text = "今天天气不好，通勤后还要见客户开会，帮我看看这些衣服怎么搭"
    first = client.post(
        "/api/life/voice-command",
        json={
            "text": text,
            "camera_id": "1182348802",
            "speaker_id": "xiaomi_speaker_01",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": text,
            "session_id": first["session_id"],
            "speaker_id": "xiaomi_speaker_01",
            "mimo_payload": {
                "source_id": "voice_bad_weather_client_commute_clip",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "white shirt",
                        "category": "top",
                        "colors": ["white"],
                        "formality": 3,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_002",
                        "name": "navy blue jacket",
                        "category": "outerwear",
                        "colors": ["blue"],
                        "formality": 2,
                        "warmth_level": 2,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                ],
                "pantry": [],
                "preferences": [],
            },
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["action"] == "responded"
    assert "今天通勤后见客户开会" in data["broadcast_text"]
    assert "天气不稳定通勤见客户" in data["broadcast_text"]
    assert "轻便耐脏外层" in data["broadcast_text"]
    assert "鞋子稳一点" in data["broadcast_text"]
    assert "雨天见客户" not in data["broadcast_text"]
    assert "南方湿热通勤" not in data["broadcast_text"]
    assert "社交场景" not in data["broadcast_text"]


def test_life_voice_command_infers_humid_social_dinner_after_visual_capture(
    tmp_path,
):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-social-dinner-context.db"
    client = _client()

    first = client.post(
        "/api/life/voice-command",
        json={
            "text": "晚上和朋友吃饭，天气有点闷热，帮我看看怎么搭",
            "camera_id": "1182348802",
            "speaker_id": "xiaomi_speaker_01",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": "晚上和朋友吃饭，天气有点闷热，帮我看看怎么搭",
            "session_id": first["session_id"],
            "speaker_id": "xiaomi_speaker_01",
            "mimo_payload": {
                "source_id": "voice_humid_social_dinner_clip",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "blue sports jacket",
                        "category": "outerwear",
                        "colors": ["blue"],
                        "formality": 1,
                        "warmth_level": 2,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_002",
                        "name": "purple long-sleeved shirt",
                        "category": "top",
                        "colors": ["purple"],
                        "formality": 2,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_003",
                        "name": "orange shorts",
                        "category": "bottom",
                        "colors": ["orange"],
                        "formality": 1,
                        "warmth_level": 0,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                ],
                "pantry": [],
                "preferences": [],
            },
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["action"] == "responded"
    assert "今晚和朋友吃饭" in data["broadcast_text"]
    assert "社交场景可以有一个亮点单品" in data["broadcast_text"]
    assert "轻薄透气" in data["broadcast_text"] or "透气" in " ".join(
        data["trigger"]["outfit"]["rationale"]
    )
    assert "今天出门" not in data["broadcast_text"]


def test_life_voice_command_infers_humid_commute_to_social_dinner_after_visual_capture(
    tmp_path,
):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-humid-commute-social-dinner.db"
    client = _client()
    text = "深圳夏天通勤上班，外面很闷热潮湿，晚上和朋友吃饭，帮我看看这些衣服怎么搭"

    first = client.post(
        "/api/life/voice-command",
        json={
            "text": text,
            "camera_id": "1182348802",
            "speaker_id": "xiaomi_speaker_01",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": text,
            "session_id": first["session_id"],
            "speaker_id": "xiaomi_speaker_01",
            "mimo_payload": {
                "source_id": "voice_humid_commute_social_dinner_clip",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "blue sports jacket",
                        "category": "outerwear",
                        "colors": ["blue"],
                        "formality": 1,
                        "warmth_level": 2,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_002",
                        "name": "purple long-sleeved shirt",
                        "category": "top",
                        "colors": ["purple"],
                        "formality": 2,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_003",
                        "name": "orange shorts",
                        "category": "bottom",
                        "colors": ["orange"],
                        "formality": 1,
                        "warmth_level": 0,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                ],
                "pantry": [],
                "preferences": [],
            },
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["action"] == "responded"
    assert "今天通勤后和朋友吃饭" in data["broadcast_text"]
    assert "湿热通勤后晚间社交" in data["broadcast_text"]
    assert "先透气排汗" in data["broadcast_text"]
    assert "晚餐保留一个亮点" in data["broadcast_text"]
    assert "客户" not in data["broadcast_text"]
    assert "视频" not in data["broadcast_text"]
    assert "雨天" not in data["broadcast_text"]


def test_life_voice_command_infers_jiangnan_plum_rain_commute_after_visual_capture(
    tmp_path,
):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-jiangnan-plum-rain-commute.db"
    client = _client()
    text = "上海江南梅雨季有点湿冷，今天通勤上班，帮我看看这些衣服怎么搭"

    first = client.post(
        "/api/life/voice-command",
        json={
            "text": text,
            "camera_id": "1182348802",
            "speaker_id": "xiaomi_speaker_01",
            "occasion": "今天日常出门",
            "weather": "请按今天当地天气给出保守建议",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": text,
            "session_id": first["session_id"],
            "speaker_id": "xiaomi_speaker_01",
            "occasion": "今天日常出门",
            "weather": "请按今天当地天气给出保守建议",
            "mimo_payload": {
                "source_id": "voice_jiangnan_plum_rain_commute_clip",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "white shirt",
                        "category": "top",
                        "colors": ["white"],
                        "formality": 2,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_002",
                        "name": "navy blue jacket",
                        "category": "outerwear",
                        "colors": ["blue"],
                        "formality": 2,
                        "warmth_level": 2,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_003",
                        "name": "gray trousers",
                        "category": "bottom",
                        "colors": ["gray"],
                        "formality": 2,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                ],
                "pantry": [],
                "preferences": [],
            },
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["action"] == "responded"
    assert "今天上班通勤" in data["broadcast_text"]
    assert "江南梅雨湿冷通勤" in data["broadcast_text"]
    assert "外层防风防潮" in data["broadcast_text"]
    assert "鞋底防滑" in data["broadcast_text"]
    assert "内搭别闷汗" in data["broadcast_text"]
    assert "今天日常出门" not in data["broadcast_text"]
    assert "请按今天当地天气" not in data["broadcast_text"]


def test_life_voice_command_infers_tianliang_commute_after_visual_capture(
    tmp_path,
):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-tianliang-commute.db"
    client = _client()
    text = "北京秋天早晚有点天凉，今天通勤上班，帮我看看这些衣服怎么搭"

    first = client.post(
        "/api/life/voice-command",
        json={
            "text": text,
            "camera_id": "1182348802",
            "speaker_id": "xiaomi_speaker_01",
            "occasion": "今天日常出门",
            "weather": "请按今天当地天气给出保守建议",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": text,
            "session_id": first["session_id"],
            "speaker_id": "xiaomi_speaker_01",
            "occasion": "今天日常出门",
            "weather": "请按今天当地天气给出保守建议",
            "mimo_payload": {
                "source_id": "voice_tianliang_commute_clip",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "blue sports jacket",
                        "category": "outerwear",
                        "colors": ["blue"],
                        "formality": 1,
                        "warmth_level": 2,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_002",
                        "name": "white shirt",
                        "category": "top",
                        "colors": ["white"],
                        "formality": 2,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_003",
                        "name": "gray trousers",
                        "category": "bottom",
                        "colors": ["gray"],
                        "formality": 2,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                ],
                "pantry": [],
                "preferences": [],
            },
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["action"] == "responded"
    assert "今天上班通勤" in data["broadcast_text"]
    assert "早晚偏凉通勤" in data["broadcast_text"]
    assert "薄外层挡风" in data["broadcast_text"]
    assert "进室内可脱" in data["broadcast_text"]
    assert "内搭别太厚" in data["broadcast_text"]
    assert "今天日常出门" not in data["broadcast_text"]
    assert "请按今天当地天气" not in data["broadcast_text"]
    assert "工作场景保留一个利落锚点" not in data["broadcast_text"]


def test_life_voice_command_infers_rainy_soccer_after_default_camera_context(
    tmp_path,
):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-rainy-soccer-context.db"
    client = _client()
    text = "今天下雨但我还要出门踢足球，帮我看看这些衣服怎么选"

    first = client.post(
        "/api/life/voice-command",
        json={
            "text": text,
            "camera_id": "1182348802",
            "speaker_id": "xiaomi_speaker_01",
            "occasion": "今天日常出门",
            "weather": "请按今天当地天气给出保守建议",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": text,
            "session_id": first["session_id"],
            "speaker_id": "xiaomi_speaker_01",
            "occasion": "今天日常出门",
            "weather": "请按今天当地天气给出保守建议",
            "mimo_payload": {
                "source_id": "voice_rainy_soccer_clip",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "blue sports jacket",
                        "category": "outerwear",
                        "colors": ["blue"],
                        "formality": 1,
                        "warmth_level": 2,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_002",
                        "name": "portugal soccer jersey",
                        "category": "top",
                        "colors": ["red"],
                        "formality": 1,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                    {
                        "id": "w_003",
                        "name": "orange shorts",
                        "category": "bottom",
                        "colors": ["orange"],
                        "formality": 1,
                        "warmth_level": 0,
                        "source_type": "camera",
                        "confidence": 0.9,
                    },
                ],
                "pantry": [],
                "preferences": [],
            },
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["action"] == "responded"
    assert "今天出门踢足球" in data["broadcast_text"]
    assert "雨天运动出行" in data["broadcast_text"]
    assert "鞋底抓地防滑" in data["broadcast_text"]
    assert "备用上衣" in data["broadcast_text"]
    assert "今天日常出门" not in data["broadcast_text"]
    assert "请按今天当地天气" not in data["broadcast_text"]


def test_life_voice_command_followup_uses_active_session_without_camera(tmp_path):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-followup.db"
    client = _client()
    first = client.post(
        "/api/life/voice-command",
        json={
            "text": OUTFIT_COMMAND,
            "speaker_id": "xiaomi_speaker_01",
            "mimo_payload": {
                "source_id": "voice_check_this_shirt",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "white shirt",
                        "category": "top",
                        "colors": ["white"],
                        "formality": 3,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    }
                ],
                "pantry": [],
                "preferences": [],
            },
            "occasion": "video meeting",
            "weather": "indoor",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": OUTFIT_FOLLOWUP,
            "session_id": first["session_id"],
            "speaker_id": "xiaomi_speaker_01",
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["session_id"] == first["session_id"]
    assert data["session_active"] is True
    assert data["domain"] == "outfit"
    assert data["action"] == "responded"
    assert data["used_last_context"] is True
    assert data["needs_visual_capture"] is False
    assert data["camera_request"] is None
    assert data["context_cache"]["hit"] is True
    assert data["context_cache"]["domain"] == "outfit"
    assert data["context_cache"]["source_type"] == "visual_result"
    assert data["context_cache"]["source_id"] == "voice_check_this_shirt"
    assert data["context_cache"]["refresh_reason"] is None
    assert data["context_cache"]["age_ms"] >= 0
    assert data["context_cache"]["expires_in_ms"] > 0
    assert data["latency"]["trigger_detect_latency_ms"] == 0
    assert data["latency"]["answer_latency_ms"] >= 0
    assert data["latency"]["total_turn_latency_ms"] >= 0
    assert data["latency"]["cache_hit"] is True
    assert data["latency"]["visual_refresh_reason"] is None
    assert data["speaker_request"]["preferred_device_id"] == "xiaomi_speaker_01"


def test_life_voice_command_followup_can_reuse_session_by_speaker(tmp_path):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-followup-by-speaker.db"
    client = _client()
    first = client.post(
        "/api/life/voice-command",
        json={
            "text": OUTFIT_COMMAND,
            "speaker_id": "xiaomi_speaker_01",
            "mimo_payload": {
                "source_id": "voice_check_this_shirt",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "white shirt",
                        "category": "top",
                        "colors": ["white"],
                        "formality": 3,
                        "warmth_level": 1,
                        "source_type": "camera",
                        "confidence": 0.9,
                    }
                ],
                "pantry": [],
                "preferences": [],
            },
            "occasion": "video meeting",
            "weather": "indoor",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": OUTFIT_FOLLOWUP,
            "speaker_id": "xiaomi_speaker_01",
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["session_id"] == first["session_id"]
    assert data["used_last_context"] is True
    assert data["context_cache"]["hit"] is True
    assert data["context_cache"]["source_id"] == "voice_check_this_shirt"
    assert data["speaker_request"]["preferred_device_id"] == "xiaomi_speaker_01"


def test_life_voice_command_visible_followup_requests_new_camera_clip(tmp_path):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-visible-followup.db"
    client = _client()
    first = client.post(
        "/api/life/voice-command",
        json={
            "text": OUTFIT_COMMAND,
            "camera_id": "1182348802",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": OUTFIT_VISIBLE_FOLLOWUP,
            "session_id": first["session_id"],
            "camera_id": "1182348802",
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["session_id"] == first["session_id"]
    assert data["action"] == "awaiting_visual_capture"
    assert data["needs_visual_capture"] is True
    assert data["camera_request"]["reason"] == "visible_object_reference"
    assert data["camera_request"]["duration_ms"] == 2000
    assert data["context_cache"]["hit"] is False
    assert data["context_cache"]["refresh_reason"] == "visible_object_reference"
    assert data["context_cache"]["source_type"] == "camera_required"
    assert data["latency"]["cache_hit"] is False
    assert data["latency"]["visual_refresh_reason"] == "visible_object_reference"


def test_life_voice_command_deduplicates_same_text_before_camera(tmp_path):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-dedup.db"
    client = _client()
    first = client.post(
        "/api/life/voice-command",
        json={
            "text": OUTFIT_COMMAND,
            "camera_id": "1182348802",
            "db_path": str(db_path),
        },
    ).json()["data"]

    response = client.post(
        "/api/life/voice-command",
        json={
            "text": OUTFIT_COMMAND,
            "session_id": first["session_id"],
            "camera_id": "1182348802",
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["session_id"] == first["session_id"]
    assert data["action"] == "duplicate_ignored"
    assert data["needs_visual_capture"] is False
    assert data["camera_request"] is None
    assert data["speaker_request"] is None


def test_life_voice_command_ignores_unrelated_first_turn(tmp_path):
    clear_life_voice_sessions()
    db_path = tmp_path / "life-voice-command-unrelated.db"

    response = _client().post(
        "/api/life/voice-command",
        json={"text": UNRELATED_COMMAND, "db_path": str(db_path)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["matched"] is False
    assert data["session_active"] is False
    assert data["action"] == "ignored"
    assert data["needs_visual_capture"] is False
    assert data["camera_request"] is None
    assert data["speaker_request"] is None


def test_life_notify_endpoint_falls_back_to_text_without_speaker_url():
    response = _client().post(
        "/api/life/notify",
        json={
            "message": "Water may be boiling; please confirm before adding dumplings.",
            "domain": "cooking",
            "urgency": "medium",
            "requires_ack": True,
            "fallback_to_text": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"] == {
        "channel": "text",
        "delivered": False,
        "fallback_text": "Water may be boiling; please confirm before adding dumplings.",
        "requires_ack": True,
        "reason": "pc_speaker_url not configured",
    }


def test_life_notify_endpoint_rejects_absolute_kitchen_claims():
    response = _client().post(
        "/api/life/notify",
        json={
            "message": "The dumplings are already cooked.",
            "domain": "cooking",
            "urgency": "medium",
        },
    )

    assert response.status_code == 422


def test_life_live_demo_endpoint_normalizes_supplied_mimo_payload(tmp_path):
    db_path = tmp_path / "life-live-demo.db"

    response = _client().post(
        "/api/life/live-demo",
        json={
            "source_id": "live_camera_probe_1182348802",
            "mimo_payload": {
                "source_id": "live_camera_probe_1182348802",
                "wardrobe": [
                    {
                        "id": "w_001",
                        "name": "白色短袖Polo衫",
                        "category": "top",
                        "colors": ["white", "red", "blue"],
                        "material_tags": ["cotton"],
                        "season_tags": ["summer", "all"],
                        "formality": "casual",
                        "warmth_level": 0,
                        "style_tags": ["sporty", "casual"],
                        "source_type": "camera",
                        "source_ref": "00:00",
                        "confidence": 0.9,
                    }
                ],
                "pantry": [],
                "preferences": {"style": "casual", "diet": "unknown"},
            },
            "persist": True,
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["source_id"] == "live_camera_probe_1182348802"
    assert data["mimo_source"] == "provided_payload"
    assert data["outfit"]["title"] == "白色短袖Polo衫"
    assert data["cooking"] is None
    assert data["persistence"]["wardrobe_count"] == 1
    assert data["persistence"]["recommendation_history_count"] == 1


def test_life_live_demo_endpoint_routes_clip_through_visual_observation(
    monkeypatch, tmp_path
):
    captured = {}

    async def fake_extract_life_assets_with_live_mimo(*, observation):
        captured["observation"] = observation
        return (
            LifeExtractionResult(
                source_id=observation.source_id,
                caption="fake live extraction",
                wardrobe_items=[
                    WardrobeItem(
                        id="w_001",
                        name="white shirt",
                        category="top",
                        colors=["white"],
                        formality=2,
                        warmth_level=1,
                        source_type="camera",
                        confidence=0.9,
                    )
                ],
                pantry_items=[],
                preferences=[],
                low_confidence_notes=[],
            ),
            "{}",
        )

    monkeypatch.setattr(
        "miloco.life.service.extract_life_assets_with_live_mimo",
        fake_extract_life_assets_with_live_mimo,
    )
    db_path = tmp_path / "life-live-demo.db"

    response = _client().post(
        "/api/life/live-demo",
        json={
            "source_id": "live_camera_probe_1182348802",
            "prompt": "focus on visible clothing",
            "clip_base64": "ZmFrZSBtcDQ=",
            "persist": True,
            "db_path": str(db_path),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    observation = captured["observation"]
    assert observation.source_id == "live_camera_probe_1182348802"
    assert observation.source_type == "short_clip"
    assert observation.media_format == "mp4"
    assert observation.prompt == "focus on visible clothing"
    assert body["data"]["outfit"]["title"] == "白色衬衫"


async def test_life_live_demo_rejects_concurrent_live_mimo_visual_request(
    monkeypatch,
    tmp_path,
):
    from miloco.life.service import run_life_live_demo

    first_mimo_started = asyncio.Event()
    release_first_mimo = asyncio.Event()
    mimo_calls = 0

    async def fake_extract_life_assets_with_live_mimo(*, observation):
        nonlocal mimo_calls
        mimo_calls += 1
        if mimo_calls == 1:
            first_mimo_started.set()
            await release_first_mimo.wait()
        return (
            LifeExtractionResult(
                source_id=observation.source_id,
                caption="fake live extraction",
                wardrobe_items=[
                    WardrobeItem(
                        id="w_001",
                        name="white shirt",
                        category="top",
                        colors=["white"],
                        formality=3,
                        warmth_level=1,
                        source_type="camera",
                        confidence=0.9,
                    )
                ],
                pantry_items=[],
                preferences=[],
                low_confidence_notes=[],
            ),
            "{}",
        )

    monkeypatch.setattr(
        "miloco.life.service.extract_life_assets_with_live_mimo",
        fake_extract_life_assets_with_live_mimo,
    )

    async def run_live_demo(source_id: str):
        return await run_life_live_demo(
            SimpleNamespace(
                source_id=source_id,
                prompt="focus on visible clothing",
                clip_base64="ZmFrZSBtcDQ=",
                mimo_payload=None,
                occasion="video meeting",
                weather="indoor",
                people_count=1,
                time_budget_minutes=30,
                persist=False,
                db_path=str(tmp_path / f"{source_id}.db"),
            )
        )

    first_task = asyncio.create_task(run_live_demo("first_live_request"))
    await asyncio.wait_for(first_mimo_started.wait(), timeout=1)

    second = await run_live_demo("second_live_request")
    release_first_mimo.set()
    first = await first_task

    assert first["outfit"]["title"] == "白色衬衫"
    assert second["reason"] == "mimo_lease_busy"
    assert second["mimo_source"] == "live_mimo_busy"
    assert second["outfit"] is None
    assert second["cooking"] is None
    assert second["low_confidence_notes"] == [
        "视觉理解正在处理上一条请求，请稍后再试。"
    ]
    assert second["mimo_lease"] == {
        "resource_type": "mimo",
        "resource_id": "visual",
        "acquired": False,
        "lease_released": True,
        "release_reason": "busy",
    }
    assert mimo_calls == 1
