# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Tests for XiaoAi scene triggers that route into life-agent voice sessions."""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from miloco.life.router import router
from miloco.voice.router import router as voice_router

OUTFIT_SCENE_TEXT = "\u5e2e\u6211\u770b\u770b\u8fd9\u4ef6\u8863\u670d\u600e\u4e48\u642d"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def _voice_client() -> TestClient:
    app = FastAPI()
    app.include_router(voice_router, prefix="/api")
    return TestClient(app)


async def test_scene_trigger_acknowledges_before_camera_capture(monkeypatch):
    from miloco.life.scene_trigger import (
        LifeSceneTriggerPayload,
        run_life_scene_trigger,
    )

    events: list[str] = []

    async def fake_play(message: str, preferred_device_id: str | None = None):
        events.append(f"play:{message}")
        return {
            "delivered": True,
            "did": preferred_device_id,
            "action": "action.5.3",
        }

    async def fake_record_camera_clip(
        *, camera_id: str, channel: int, duration_ms: int
    ):
        events.append(f"record:{camera_id}:{channel}:{duration_ms}")
        return b"fake mp4"

    run_voice_command = AsyncMock(
        side_effect=[
            {
                "matched": True,
                "session_id": "life_voice_001",
                "domain": "outfit",
                "action": "awaiting_visual_capture",
                "needs_visual_capture": True,
                "camera_request": {
                    "camera_id": "camera_01",
                    "channel": 0,
                    "duration_ms": 2000,
                    "session_id": "life_voice_001",
                },
                "context_cache": {
                    "hit": False,
                    "source_type": "camera_required",
                    "source_id": None,
                    "refresh_reason": "visible_object_reference",
                },
                "speaker_request": None,
            },
            {
                "matched": True,
                "session_id": "life_voice_001",
                "domain": "outfit",
                "action": "responded",
                "needs_visual_capture": False,
                "camera_request": None,
                "broadcast_text": "\u7a7f\u642d\u5efa\u8bae\uff1a\u53ef\u4ee5\u642d\u914d\u8fd9\u4ef6\u4e0a\u8863\u3002",
                "speaker_request": {
                    "channel": "xiaomi_speaker",
                    "preferred_device_id": "speaker_01",
                    "message": "\u7a7f\u642d\u5efa\u8bae\uff1a\u53ef\u4ee5\u642d\u914d\u8fd9\u4ef6\u4e0a\u8863\u3002",
                    "requires_ack": False,
                },
                "used_last_context": False,
                "context_cache": {
                    "hit": False,
                    "source_type": "visual_result",
                    "source_id": "scene_camera_camera_01",
                    "refresh_reason": "visual_input",
                },
            },
        ]
    )

    monkeypatch.setattr(
        "miloco.life.scene_trigger.play_xiaomi_speaker_message", fake_play
    )
    monkeypatch.setattr(
        "miloco.life.scene_trigger.record_life_camera_clip", fake_record_camera_clip
    )
    monkeypatch.setattr(
        "miloco.life.scene_trigger.run_life_voice_command", run_voice_command
    )

    result = await run_life_scene_trigger(
        LifeSceneTriggerPayload(
            intent="outfit_check",
            text=OUTFIT_SCENE_TEXT,
            speaker_id="speaker_01",
            camera_id="camera_01",
        )
    )

    assert events == [
        "play:\u597d\u7684\uff0c\u6211\u770b\u4e00\u4e0b\u3002",
        "record:camera_01:0:2000",
        "play:\u7a7f\u642d\u5efa\u8bae\uff1a\u53ef\u4ee5\u642d\u914d\u8fd9\u4ef6\u4e0a\u8863\u3002",
    ]
    assert result["action"] == "responded"
    assert (
        result["ack"]["message"] == "\u597d\u7684\uff0c\u6211\u770b\u4e00\u4e0b\u3002"
    )
    assert result["cache_hit"] is False
    assert result["visual_refresh_reason"] == "visible_object_reference"
    assert result["first_context_cache"]["source_type"] == "camera_required"
    assert result["final_context_cache"]["source_type"] == "visual_result"
    assert result["visual_capture"] == {
        "camera_id": "camera_01",
        "channel": 0,
        "duration_ms": 2000,
        "bytes": len(b"fake mp4"),
        "lease_released": True,
        "release_reason": "completed",
        "lease_duration_ms": result["visual_capture"]["lease_duration_ms"],
        "visual_capture_started_at_ms": result["visual_capture"][
            "visual_capture_started_at_ms"
        ],
        "visual_capture_ended_at_ms": result["visual_capture"][
            "visual_capture_ended_at_ms"
        ],
        "lease": {
            "resource_type": "camera",
            "resource_id": "camera_01",
            "channel": 0,
            "duration_ms": 2000,
            "released": True,
            "release_reason": "completed",
            "started_at_ms": result["visual_capture"]["lease"]["started_at_ms"],
            "ended_at_ms": result["visual_capture"]["lease"]["ended_at_ms"],
            "lease_duration_ms": result["visual_capture"]["lease"]["lease_duration_ms"],
        },
    }
    assert result["visual_capture"]["visual_capture_started_at_ms"] >= 0
    assert (
        result["visual_capture"]["visual_capture_ended_at_ms"]
        >= result["visual_capture"]["visual_capture_started_at_ms"]
    )
    assert (
        result["visual_capture"]["lease_duration_ms"]
        == result["visual_capture"]["visual_capture_ended_at_ms"]
        - result["visual_capture"]["visual_capture_started_at_ms"]
    )
    assert (
        result["visual_capture"]["lease"]["started_at_ms"]
        == result["visual_capture"]["visual_capture_started_at_ms"]
    )
    assert (
        result["visual_capture"]["lease"]["ended_at_ms"]
        == result["visual_capture"]["visual_capture_ended_at_ms"]
    )
    assert (
        result["visual_capture"]["lease"]["lease_duration_ms"]
        == result["visual_capture"]["lease_duration_ms"]
    )
    second_payload = run_voice_command.await_args_list[1].args[0]
    assert second_payload.session_id == "life_voice_001"
    assert second_payload.clip_base64 == base64.b64encode(b"fake mp4").decode("ascii")


async def test_scene_trigger_releases_camera_lease_when_capture_fails(monkeypatch):
    from miloco.life.scene_trigger import (
        LifeSceneTriggerPayload,
        run_life_scene_trigger,
    )

    async def fake_record_camera_clip(
        *, camera_id: str, channel: int, duration_ms: int
    ):
        raise RuntimeError("camera busy")

    run_voice_command = AsyncMock(
        return_value={
            "matched": True,
            "session_id": "life_voice_capture_failure",
            "domain": "outfit",
            "action": "awaiting_visual_capture",
            "needs_visual_capture": True,
            "camera_request": {
                "camera_id": "camera_01",
                "channel": 0,
                "duration_ms": 2000,
                "session_id": "life_voice_capture_failure",
            },
            "speaker_request": None,
        }
    )
    speaker_play = AsyncMock(return_value={"delivered": False, "reason": "suppressed"})

    monkeypatch.setattr(
        "miloco.life.scene_trigger.record_life_camera_clip", fake_record_camera_clip
    )
    monkeypatch.setattr(
        "miloco.life.scene_trigger.run_life_voice_command", run_voice_command
    )
    monkeypatch.setattr(
        "miloco.life.scene_trigger.play_xiaomi_speaker_message", speaker_play
    )

    result = await run_life_scene_trigger(
        LifeSceneTriggerPayload(
            intent="outfit_check",
            text=OUTFIT_SCENE_TEXT,
            speaker_id="speaker_01",
            camera_id="camera_01",
            suppress_speaker=True,
        )
    )

    assert result["action"] == "responded"
    assert result["visual_capture"] == {
        "camera_id": "camera_01",
        "channel": 0,
        "duration_ms": 2000,
        "bytes": 0,
        "error": "camera busy",
        "lease_released": True,
        "release_reason": "failed",
        "lease_duration_ms": result["visual_capture"]["lease_duration_ms"],
        "visual_capture_started_at_ms": result["visual_capture"][
            "visual_capture_started_at_ms"
        ],
        "visual_capture_ended_at_ms": result["visual_capture"][
            "visual_capture_ended_at_ms"
        ],
        "lease": {
            "resource_type": "camera",
            "resource_id": "camera_01",
            "channel": 0,
            "duration_ms": 2000,
            "released": True,
            "release_reason": "failed",
            "started_at_ms": result["visual_capture"]["lease"]["started_at_ms"],
            "ended_at_ms": result["visual_capture"]["lease"]["ended_at_ms"],
            "lease_duration_ms": result["visual_capture"]["lease"]["lease_duration_ms"],
        },
    }
    assert result["visual_capture"]["visual_capture_started_at_ms"] >= 0
    assert (
        result["visual_capture"]["visual_capture_ended_at_ms"]
        >= result["visual_capture"]["visual_capture_started_at_ms"]
    )
    assert (
        result["visual_capture"]["lease_duration_ms"]
        == result["visual_capture"]["visual_capture_ended_at_ms"]
        - result["visual_capture"]["visual_capture_started_at_ms"]
    )
    assert result["final"]["reason"] == "camera_capture_failed"
    assert (
        result["final_playback"]["message"]
        == "\u6211\u8fd9\u8fb9\u6682\u65f6\u6ca1\u6709\u53d6\u5230\u6444\u50cf\u5934\u753b\u9762\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002"
    )
    camera_stage = next(
        stage
        for stage in result["timing"]["stages"]
        if stage["stage"] == "camera_capture"
    )
    assert camera_stage["status"] == "failed"
    assert camera_stage["error"] == "camera busy"
    assert run_voice_command.await_count == 1


async def test_scene_trigger_rejects_concurrent_capture_for_same_camera(monkeypatch):
    from miloco.life.scene_trigger import (
        LifeSceneTriggerPayload,
        run_life_scene_trigger,
    )

    first_recording_started = asyncio.Event()
    release_first_recording = asyncio.Event()
    record_calls = 0

    async def fake_record_camera_clip(
        *, camera_id: str, channel: int, duration_ms: int
    ):
        nonlocal record_calls
        record_calls += 1
        if record_calls == 1:
            first_recording_started.set()
            await release_first_recording.wait()
            return b"fake mp4"
        return b"unexpected second mp4"

    initial_count = 0

    async def fake_run_voice_command(voice_payload):
        nonlocal initial_count
        if voice_payload.clip_base64:
            return {
                "matched": True,
                "session_id": voice_payload.session_id,
                "domain": "outfit",
                "action": "responded",
                "needs_visual_capture": False,
                "camera_request": None,
                "broadcast_text": "\u7a7f\u642d\u5efa\u8bae\uff1a\u53ef\u4ee5\u9009\u8fd9\u4ef6\u3002",
                "speaker_request": {
                    "channel": "xiaomi_speaker",
                    "preferred_device_id": "speaker_01",
                    "message": "\u7a7f\u642d\u5efa\u8bae\uff1a\u53ef\u4ee5\u9009\u8fd9\u4ef6\u3002",
                    "requires_ack": False,
                },
            }

        initial_count += 1
        return {
            "matched": True,
            "session_id": f"life_voice_lock_{initial_count:03d}",
            "domain": "outfit",
            "action": "awaiting_visual_capture",
            "needs_visual_capture": True,
            "camera_request": {
                "camera_id": "camera_01",
                "channel": 0,
                "duration_ms": 2000,
                "session_id": f"life_voice_lock_{initial_count:03d}",
            },
            "speaker_request": None,
        }

    speaker_play = AsyncMock(return_value={"delivered": False, "reason": "suppressed"})

    monkeypatch.setattr(
        "miloco.life.scene_trigger.record_life_camera_clip", fake_record_camera_clip
    )
    monkeypatch.setattr(
        "miloco.life.scene_trigger.run_life_voice_command", fake_run_voice_command
    )
    monkeypatch.setattr(
        "miloco.life.scene_trigger.play_xiaomi_speaker_message", speaker_play
    )

    payload = LifeSceneTriggerPayload(
        intent="outfit_check",
        text=OUTFIT_SCENE_TEXT,
        speaker_id="speaker_01",
        camera_id="camera_01",
        suppress_speaker=True,
    )
    first_task = asyncio.create_task(run_life_scene_trigger(payload))
    await asyncio.wait_for(first_recording_started.wait(), timeout=1)

    second_result = await run_life_scene_trigger(payload)
    release_first_recording.set()
    first_result = await first_task

    assert first_result["action"] == "responded"
    assert first_result["visual_capture"]["release_reason"] == "completed"
    assert second_result["action"] == "responded"
    assert second_result["final"]["reason"] == "camera_lease_busy"
    assert second_result["visual_capture"]["release_reason"] == "busy"
    assert second_result["visual_capture"]["lease_released"] is True
    assert second_result["visual_capture"]["bytes"] == 0
    assert record_calls == 1


async def test_scene_speaker_playback_rejects_concurrent_message_for_same_speaker(
    monkeypatch,
):
    from miloco.life.scene_trigger import _play_scene_message

    first_playback_started = asyncio.Event()
    release_first_playback = asyncio.Event()
    play_calls = 0

    async def fake_play(message: str, preferred_device_id: str | None = None):
        nonlocal play_calls
        play_calls += 1
        if play_calls == 1:
            first_playback_started.set()
            await release_first_playback.wait()
            return {
                "delivered": True,
                "did": preferred_device_id,
                "message": message,
            }
        return {
            "delivered": True,
            "did": preferred_device_id,
            "message": "unexpected second playback",
        }

    monkeypatch.setattr(
        "miloco.life.scene_trigger.play_xiaomi_speaker_message", fake_play
    )

    first_task = asyncio.create_task(
        _play_scene_message(
            "\u7b2c\u4e00\u6761\u64ad\u62a5",
            speaker_id="speaker_01",
            suppress=False,
        )
    )
    await asyncio.wait_for(first_playback_started.wait(), timeout=1)

    second_result = await _play_scene_message(
        "\u7b2c\u4e8c\u6761\u64ad\u62a5",
        speaker_id="speaker_01",
        suppress=False,
    )
    release_first_playback.set()
    first_result = await first_task

    assert first_result["delivered"] is True
    assert second_result == {
        "delivered": False,
        "reason": "speaker_lease_busy",
        "speaker_id": "speaker_01",
        "message": "\u7b2c\u4e8c\u6761\u64ad\u62a5",
    }
    assert play_calls == 1


async def test_scene_trigger_reports_stage_timing_for_latency_diagnostics(monkeypatch):
    from miloco.life.scene_trigger import (
        LifeSceneTriggerPayload,
        run_life_scene_trigger,
    )

    async def fake_play(message: str, preferred_device_id: str | None = None):
        return {
            "delivered": True,
            "did": preferred_device_id,
            "action": "action.5.3",
        }

    async def fake_record_camera_clip(
        *, camera_id: str, channel: int, duration_ms: int
    ):
        return b"fake mp4"

    run_voice_command = AsyncMock(
        side_effect=[
            {
                "matched": True,
                "session_id": "life_voice_timing",
                "domain": "outfit",
                "action": "awaiting_visual_capture",
                "needs_visual_capture": True,
                "camera_request": {
                    "camera_id": "camera_01",
                    "channel": 0,
                    "duration_ms": 2000,
                    "session_id": "life_voice_timing",
                },
                "speaker_request": None,
            },
            {
                "matched": True,
                "session_id": "life_voice_timing",
                "domain": "outfit",
                "action": "responded",
                "needs_visual_capture": False,
                "camera_request": None,
                "broadcast_text": "\u7a7f\u642d\u5efa\u8bae\uff1a\u9009\u8fd9\u4ef6\u4e0a\u8863\u3002",
                "speaker_request": {
                    "channel": "xiaomi_speaker",
                    "preferred_device_id": "speaker_01",
                    "message": "\u7a7f\u642d\u5efa\u8bae\uff1a\u9009\u8fd9\u4ef6\u4e0a\u8863\u3002",
                    "requires_ack": False,
                },
            },
        ]
    )

    monkeypatch.setattr(
        "miloco.life.scene_trigger.play_xiaomi_speaker_message", fake_play
    )
    monkeypatch.setattr(
        "miloco.life.scene_trigger.record_life_camera_clip", fake_record_camera_clip
    )
    monkeypatch.setattr(
        "miloco.life.scene_trigger.run_life_voice_command", run_voice_command
    )

    result = await run_life_scene_trigger(
        LifeSceneTriggerPayload(
            intent="outfit_check",
            text=OUTFIT_SCENE_TEXT,
            speaker_id="speaker_01",
            camera_id="camera_01",
        )
    )

    timing = result["timing"]
    stages = timing["stages"]
    assert [stage["stage"] for stage in stages] == [
        "ack_playback",
        "agent_initial",
        "camera_capture",
        "agent_visual",
        "final_playback",
    ]
    assert timing["total_ms"] >= 0
    assert timing["ack_started_ms"] == stages[0]["started_ms"]
    assert timing["first_response_ready_ms"] == stages[1]["ended_ms"]
    assert timing["final_response_ready_ms"] == stages[3]["ended_ms"]
    assert timing["final_playback_ready_ms"] == stages[-1]["ended_ms"]
    assert timing["trigger_detect_latency_ms"] == 0
    assert timing["silence_before_ack_ms"] == stages[0]["started_ms"]
    assert timing["ack_latency_ms"] == stages[0]["duration_ms"]
    assert timing["camera_lease_ms"] == stages[2]["duration_ms"]
    assert timing["mimo_latency_ms"] == stages[3]["duration_ms"]
    assert timing["answer_latency_ms"] == stages[3]["duration_ms"]
    assert timing["tts_first_audio_ms"] == stages[-1]["duration_ms"]
    assert timing["tts_playback_duration_ms"] == stages[-1]["duration_ms"]
    assert timing["total_turn_latency_ms"] == timing["total_ms"]
    assert timing["cache_hit"] is False
    assert timing["visual_refresh_reason"] is None
    for stage in stages:
        assert set(stage) == {
            "stage",
            "started_ms",
            "ended_ms",
            "duration_ms",
            "status",
        }
        assert stage["status"] == "completed"
        assert stage["started_ms"] <= stage["ended_ms"]
        assert stage["duration_ms"] == stage["ended_ms"] - stage["started_ms"]


async def test_scene_trigger_inventory_intent_skips_camera(monkeypatch):
    from miloco.life.scene_trigger import (
        LifeSceneTriggerPayload,
        run_life_scene_trigger,
    )

    record_camera_clip = AsyncMock()
    run_voice_command = AsyncMock(
        return_value={
            "matched": True,
            "session_id": "life_voice_002",
            "domain": "outfit",
            "action": "responded",
            "needs_visual_capture": False,
            "camera_request": None,
            "broadcast_text": "\u7a7f\u642d\u5efa\u8bae\uff1a\u4eca\u5929\u53ef\u4ee5\u7a7f\u767d\u8272\u886c\u886b\u3002",
            "speaker_request": {
                "channel": "xiaomi_speaker",
                "preferred_device_id": "speaker_01",
                "message": "\u7a7f\u642d\u5efa\u8bae\uff1a\u4eca\u5929\u53ef\u4ee5\u7a7f\u767d\u8272\u886c\u886b\u3002",
                "requires_ack": False,
            },
            "used_last_context": True,
            "context_cache": {
                "hit": True,
                "source_type": "inventory_result",
                "source_id": "stored_wardrobe",
                "refresh_reason": None,
            },
        }
    )
    speaker_play = AsyncMock(return_value={"delivered": True})

    monkeypatch.setattr(
        "miloco.life.scene_trigger.record_life_camera_clip", record_camera_clip
    )
    monkeypatch.setattr(
        "miloco.life.scene_trigger.run_life_voice_command", run_voice_command
    )
    monkeypatch.setattr(
        "miloco.life.scene_trigger.play_xiaomi_speaker_message", speaker_play
    )

    result = await run_life_scene_trigger(
        LifeSceneTriggerPayload(intent="outfit_suggest", speaker_id="speaker_01")
    )

    record_camera_clip.assert_not_awaited()
    first_payload = run_voice_command.await_args.args[0]
    assert first_payload.speaker_id == "speaker_01"
    assert result["cache_hit"] is True
    assert result["visual_refresh_reason"] is None
    assert result["first_context_cache"]["hit"] is True
    assert result["final_context_cache"]["hit"] is True
    assert result["visual_capture"] is None
    assert (
        speaker_play.await_args_list[0].args[0]
        == "\u597d\u7684\uff0c\u6211\u6574\u7406\u4e00\u4e0b\u7a7f\u642d\u5efa\u8bae\u3002"
    )
    assert (
        speaker_play.await_args_list[1].args[0]
        == "\u7a7f\u642d\u5efa\u8bae\uff1a\u4eca\u5929\u53ef\u4ee5\u7a7f\u767d\u8272\u886c\u886b\u3002"
    )


def test_life_scene_trigger_endpoint_accepts_xiaoai_scene_payload(monkeypatch):
    async def fake_run_scene_trigger(payload):
        return {
            "run_id": "scene_001",
            "intent": payload.intent,
            "action": "responded",
            "ack": {"message": payload.ack_message},
            "visual_capture": None,
            "final": {"action": "responded"},
        }

    monkeypatch.setattr(
        "miloco.life.router.run_life_scene_trigger_service", fake_run_scene_trigger
    )

    response = _client().post(
        "/api/life/scene-trigger",
        json={
            "intent": "outfit_check",
            "text": OUTFIT_SCENE_TEXT,
            "speaker_id": "speaker_01",
            "camera_id": "camera_01",
            "ack_message": "\u6536\u5230\uff0c\u6211\u770b\u4e00\u4e0b\u3002",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["intent"] == "outfit_check"
    assert (
        body["data"]["ack"]["message"]
        == "\u6536\u5230\uff0c\u6211\u770b\u4e00\u4e0b\u3002"
    )


def test_voice_scene_trigger_post_alias_accepts_xiaoai_scene_payload(monkeypatch):
    async def fake_run_scene_trigger(payload):
        return {
            "run_id": "scene_voice_post_001",
            "intent": payload.intent,
            "action": "responded",
            "ack": {"message": payload.ack_message},
            "visual_capture": None,
            "final": {"action": "responded"},
        }

    monkeypatch.setattr(
        "miloco.voice.router.run_life_scene_trigger_service", fake_run_scene_trigger
    )

    response = _voice_client().post(
        "/api/voice/scene-trigger",
        json={
            "intent": "outfit_check",
            "text": OUTFIT_SCENE_TEXT,
            "speaker_id": "speaker_01",
            "camera_id": "camera_01",
            "ack_message": "\u6536\u5230\uff0c\u6211\u770b\u4e00\u4e0b\u3002",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["intent"] == "outfit_check"
    assert (
        body["data"]["ack"]["message"]
        == "\u6536\u5230\uff0c\u6211\u770b\u4e00\u4e0b\u3002"
    )


def test_voice_command_alias_accepts_asr_text_payload(monkeypatch):
    captured = {}

    async def fake_run_voice_command(payload):
        captured["payload"] = payload
        return {
            "matched": True,
            "domain": "outfit",
            "action": "awaiting_visual_capture",
            "needs_visual_capture": True,
            "camera_request": {
                "camera_id": payload.camera_id,
                "submit_endpoint": "/api/life/voice-command",
            },
            "speaker_request": None,
        }

    monkeypatch.setattr(
        "miloco.voice.router.run_life_voice_command_service",
        fake_run_voice_command,
    )

    response = _voice_client().post(
        "/api/voice/command",
        json={
            "text": "\u5e2e\u6211\u770b\u770b\u8fd9\u4ef6\u8863\u670d\u600e\u4e48\u642d",
            "speaker_id": "speaker_01",
            "camera_id": "camera_01",
            "trigger_source": "voice_intent",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["domain"] == "outfit"
    assert body["data"]["needs_visual_capture"] is True
    payload = captured["payload"]
    assert (
        payload.text
        == "\u5e2e\u6211\u770b\u770b\u8fd9\u4ef6\u8863\u670d\u600e\u4e48\u642d"
    )
    assert payload.speaker_id == "speaker_01"
    assert payload.camera_id == "camera_01"
    assert payload.trigger_source == "voice_intent"


def test_voice_scene_trigger_get_accepts_url_query_payload(monkeypatch):
    captured = {}

    async def fake_run_scene_trigger(payload):
        captured["payload"] = payload
        return {
            "run_id": "scene_voice_get_001",
            "intent": payload.intent,
            "action": "responded",
            "ack": {"message": payload.ack_message},
            "visual_capture": None,
            "final": {"action": "responded"},
        }

    monkeypatch.setattr(
        "miloco.voice.router.run_life_scene_trigger_service", fake_run_scene_trigger
    )

    response = _voice_client().get(
        "/api/voice/scene-trigger",
        params={
            "intent": "cooking_suggest",
            "speaker_id": "speaker_01",
            "camera_id": "camera_01",
            "suppress_speaker": "true",
            "db_path": "data/life-demo.db",
            "async_mode": "false",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    payload = captured["payload"]
    assert payload.intent == "cooking_suggest"
    assert payload.speaker_id == "speaker_01"
    assert payload.camera_id == "camera_01"
    assert payload.suppress_speaker is True
    assert payload.db_path == "data/life-demo.db"


def test_voice_scene_trigger_get_defaults_to_async_accepted(monkeypatch):
    enqueued = {}

    def fake_enqueue_scene_trigger(payload):
        enqueued["payload"] = payload
        return {
            "run_id": "scene_async_get_001",
            "intent": payload.intent,
            "action": "accepted",
            "async_mode": True,
            "status": "accepted",
            "status_endpoint": "/api/voice/scene-runs/scene_async_get_001",
        }

    run_scene_trigger = AsyncMock()
    monkeypatch.setattr(
        "miloco.voice.router.enqueue_life_scene_trigger_service",
        fake_enqueue_scene_trigger,
    )
    monkeypatch.setattr(
        "miloco.voice.router.run_life_scene_trigger_service", run_scene_trigger
    )

    response = _voice_client().get(
        "/api/voice/scene-trigger",
        params={
            "intent": "outfit_check",
            "speaker_id": "speaker_01",
            "camera_id": "camera_01",
            "suppress_speaker": "true",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"] == {
        "run_id": "scene_async_get_001",
        "intent": "outfit_check",
        "action": "accepted",
        "async_mode": True,
        "status": "accepted",
        "status_endpoint": "/api/voice/scene-runs/scene_async_get_001",
    }
    assert enqueued["payload"].intent == "outfit_check"
    run_scene_trigger.assert_not_awaited()


def test_voice_scene_short_alias_uses_env_device_ids_and_async(monkeypatch):
    enqueued = {}

    def fake_enqueue_scene_trigger(payload):
        enqueued["payload"] = payload
        return {
            "run_id": "scene_alias_outfit_check_001",
            "intent": payload.intent,
            "action": "accepted",
            "async_mode": True,
            "status": "accepted",
            "status_endpoint": "/api/voice/scene-runs/scene_alias_outfit_check_001",
        }

    run_scene_trigger = AsyncMock()
    monkeypatch.setenv("MILOCO_LIFE_XIAOMI_SPEAKER_ID", "speaker_env_01")
    monkeypatch.setenv("MILOCO_LIFE_CAMERA_ID", "camera_env_01")
    monkeypatch.setattr(
        "miloco.voice.router.enqueue_life_scene_trigger_service",
        fake_enqueue_scene_trigger,
    )
    monkeypatch.setattr(
        "miloco.voice.router.run_life_scene_trigger_service", run_scene_trigger
    )

    response = _voice_client().get("/api/voice/scene/outfit-check")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "accepted"
    assert body["data"]["intent"] == "outfit_check"
    assert body["data"]["action"] == "accepted"
    payload = enqueued["payload"]
    assert payload.intent == "outfit_check"
    assert payload.speaker_id == "speaker_env_01"
    assert payload.camera_id == "camera_env_01"
    assert payload.suppress_speaker is False
    run_scene_trigger.assert_not_awaited()


def test_voice_scene_short_alias_no_visual_omits_camera_and_can_be_silent(monkeypatch):
    enqueued = {}

    def fake_enqueue_scene_trigger(payload):
        enqueued["payload"] = payload
        return {
            "run_id": "scene_alias_outfit_suggest_001",
            "intent": payload.intent,
            "action": "accepted",
            "async_mode": True,
            "status": "accepted",
            "status_endpoint": "/api/voice/scene-runs/scene_alias_outfit_suggest_001",
        }

    monkeypatch.setenv("MILOCO_LIFE_XIAOMI_SPEAKER_ID", "speaker_env_01")
    monkeypatch.setenv("MILOCO_LIFE_CAMERA_ID", "camera_env_01")
    monkeypatch.setattr(
        "miloco.voice.router.enqueue_life_scene_trigger_service",
        fake_enqueue_scene_trigger,
    )

    response = _voice_client().get(
        "/api/voice/scene/outfit-suggest",
        params={"suppress_speaker": "true"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["intent"] == "outfit_suggest"
    payload = enqueued["payload"]
    assert payload.intent == "outfit_suggest"
    assert payload.speaker_id == "speaker_env_01"
    assert payload.camera_id is None
    assert payload.suppress_speaker is True


def test_voice_scene_defaults_endpoint_exposes_queryless_device_defaults(monkeypatch):
    monkeypatch.setenv("MILOCO_LIFE_XIAOMI_SPEAKER_ID", "speaker_env_01")
    monkeypatch.setenv("MILOCO_LIFE_CAMERA_ID", "camera_env_01")

    response = _voice_client().get("/api/voice/scene-defaults")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"] == {
        "speaker_id": "speaker_env_01",
        "camera_id": "camera_env_01",
        "default_speaker_outfit_suggest": "/api/voice/scene/outfit-suggest",
        "default_camera_speaker_outfit_check": "/api/voice/scene/outfit-check",
        "default_speaker_cooking_suggest": "/api/voice/scene/cooking-suggest",
        "default_camera_speaker_cooking_check": "/api/voice/scene/cooking-check",
        "default_silent_outfit_suggest": "/api/voice/scene-silent/outfit-suggest",
        "default_silent_cooking_suggest": "/api/voice/scene-silent/cooking-suggest",
        "scenes": [
            {
                "slug": "outfit-suggest",
                "intent": "outfit_suggest",
                "path": "/api/voice/scene/outfit-suggest",
                "silent_path": "/api/voice/scene-silent/outfit-suggest",
                "requires_visual": False,
                "uses_speaker": True,
                "async_mode": True,
            },
            {
                "slug": "outfit-check",
                "intent": "outfit_check",
                "path": "/api/voice/scene/outfit-check",
                "silent_path": "/api/voice/scene-silent/outfit-check",
                "requires_visual": True,
                "uses_speaker": True,
                "async_mode": True,
            },
            {
                "slug": "cooking-suggest",
                "intent": "cooking_suggest",
                "path": "/api/voice/scene/cooking-suggest",
                "silent_path": "/api/voice/scene-silent/cooking-suggest",
                "requires_visual": False,
                "uses_speaker": True,
                "async_mode": True,
            },
            {
                "slug": "cooking-check",
                "intent": "cooking_check",
                "path": "/api/voice/scene/cooking-check",
                "silent_path": "/api/voice/scene-silent/cooking-check",
                "requires_visual": True,
                "uses_speaker": True,
                "async_mode": True,
            },
        ],
        "trigger_gateway": {
            "enabled": False,
            "mode": "manual_scene_event",
            "idle_poll_interval_ms": 30000,
            "active_poll_interval_ms": 2000,
            "ttl_seconds": 90,
            "max_empty_backoff_ms": 120000,
            "autostart_allowed": False,
            "idle_resource_audit_required": True,
            "idle_resource_audit_passed": False,
            "polls_trigger_metadata_only": True,
            "forbidden_during_detection": [
                "camera",
                "speaker",
                "mimo",
                "life_agent",
            ],
        },
        "device_state_watcher": {
            "enabled": False,
            "ready": False,
            "autostart_allowed": False,
            "running": False,
            "trigger_source": "device_state",
            "intent": "outfit_suggest",
            "did_configured": False,
            "iid_configured": False,
            "target_value_configured": False,
            "poll_interval_ms": 30000,
            "cooldown_ms": 120000,
            "edge_trigger": True,
            "baseline_required": True,
            "rearm_required": True,
            "error_backoff_enabled": True,
            "polls_device_status_only": True,
            "forbidden_during_idle_poll": [
                "camera",
                "speaker",
                "mimo",
                "life_agent",
            ],
            "missing": [
                "audit_passed",
                "did",
                "iid",
                "target_value",
            ],
            "last_poll": None,
            "next_poll_after_ms": None,
        },
    }


def test_voice_scene_defaults_reads_safe_trigger_gateway_env(monkeypatch):
    monkeypatch.setenv("MILOCO_LIFE_TRIGGER_GATEWAY_ENABLED", "true")
    monkeypatch.setenv("MILOCO_LIFE_TRIGGER_GATEWAY_MODE", "miot_scene_poll")
    monkeypatch.setenv("MILOCO_LIFE_IDLE_POLL_INTERVAL_MS", "45000")
    monkeypatch.setenv("MILOCO_LIFE_ACTIVE_POLL_INTERVAL_MS", "1500")
    monkeypatch.setenv("MILOCO_LIFE_TRIGGER_TTL_SECONDS", "60")
    monkeypatch.setenv("MILOCO_LIFE_MAX_EMPTY_BACKOFF_MS", "180000")
    monkeypatch.setenv("MILOCO_LIFE_IDLE_RESOURCE_AUDIT_PASSED", "true")

    response = _voice_client().get("/api/voice/scene-defaults")

    assert response.status_code == 200
    gateway = response.json()["data"]["trigger_gateway"]
    assert gateway == {
        "enabled": True,
        "mode": "miot_scene_poll",
        "idle_poll_interval_ms": 45000,
        "active_poll_interval_ms": 1500,
        "ttl_seconds": 60,
        "max_empty_backoff_ms": 180000,
        "autostart_allowed": True,
        "idle_resource_audit_required": True,
        "idle_resource_audit_passed": True,
        "polls_trigger_metadata_only": True,
        "forbidden_during_detection": [
            "camera",
            "speaker",
            "mimo",
            "life_agent",
        ],
    }


def test_scene_trigger_accepts_device_state_trigger_source():
    from miloco.life.router import LifeSceneTriggerRequest

    request = LifeSceneTriggerRequest(
        intent="outfit_suggest",
        trigger_source="device_state",
    )

    payload = request.to_scene_payload()
    assert payload.trigger_source == "device_state"


def test_device_state_watcher_config_requires_safety_and_binding(monkeypatch):
    from miloco.life.device_state_watcher import read_device_state_watcher_config

    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_WATCHER_ENABLED", "true")

    missing = read_device_state_watcher_config()

    assert missing.enabled is True
    assert missing.autostart_allowed is False
    assert missing.ready is False
    assert missing.diagnostics()["missing"] == [
        "audit_passed",
        "did",
        "iid",
        "target_value",
    ]

    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_WATCHER_AUDIT_PASSED", "true")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_DID", "2119430286")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_IID", "2")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE", "true")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_INTENT", "outfit_suggest")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_POLL_INTERVAL_MS", "45000")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_COOLDOWN_MS", "180000")

    ready = read_device_state_watcher_config()

    assert ready.ready is True
    assert ready.autostart_allowed is True
    assert ready.trigger_source == "device_state"
    assert ready.intent == "outfit_suggest"
    assert ready.did == "2119430286"
    assert ready.iid == "2"
    assert ready.target_value == "true"
    assert ready.poll_interval_ms == 45000
    assert ready.cooldown_ms == 180000
    assert ready.diagnostics()["missing"] == []


def test_voice_scene_defaults_exposes_device_state_watcher_summary(monkeypatch):
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_WATCHER_ENABLED", "true")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_WATCHER_AUDIT_PASSED", "true")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_DID", "2119430286")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_IID", "2")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE", "true")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_INTENT", "outfit_suggest")

    response = _voice_client().get("/api/voice/scene-defaults")

    assert response.status_code == 200
    watcher = response.json()["data"]["device_state_watcher"]
    assert watcher == {
        "enabled": True,
        "ready": True,
        "autostart_allowed": True,
        "running": False,
        "trigger_source": "device_state",
        "intent": "outfit_suggest",
        "did_configured": True,
        "iid_configured": True,
        "target_value_configured": True,
        "poll_interval_ms": 30000,
        "cooldown_ms": 120000,
        "edge_trigger": True,
        "baseline_required": True,
        "rearm_required": True,
        "error_backoff_enabled": True,
        "polls_device_status_only": True,
        "forbidden_during_idle_poll": [
            "camera",
            "speaker",
            "mimo",
            "life_agent",
        ],
        "missing": [],
        "last_poll": None,
        "next_poll_after_ms": None,
    }


def test_voice_scene_defaults_reads_registered_device_state_watcher_loop(monkeypatch):
    from miloco.voice.router import set_device_state_watcher_loop_service

    class FakeLoop:
        def status(self):
            return {
                "enabled": True,
                "ready": True,
                "autostart_allowed": True,
                "running": True,
                "trigger_source": "device_state",
                "intent": "outfit_suggest",
                "did_configured": True,
                "iid_configured": True,
                "target_value_configured": True,
                "poll_interval_ms": 30000,
                "cooldown_ms": 120000,
                "edge_trigger": True,
                "baseline_required": True,
                "rearm_required": True,
                "error_backoff_enabled": True,
                "polls_device_status_only": True,
                "forbidden_during_idle_poll": [
                    "camera",
                    "speaker",
                    "mimo",
                    "life_agent",
                ],
                "missing": [],
                "last_poll": {
                    "action": "baseline",
                    "triggered": False,
                    "next_poll_after_ms": 12345,
                },
                "next_poll_after_ms": 12345,
            }

    set_device_state_watcher_loop_service(FakeLoop())
    try:
        response = _voice_client().get("/api/voice/scene-defaults")

        assert response.status_code == 200
        watcher = response.json()["data"]["device_state_watcher"]
        assert watcher["running"] is True
        assert watcher["last_poll"] == {
            "action": "baseline",
            "triggered": False,
            "next_poll_after_ms": 12345,
        }
        assert watcher["next_poll_after_ms"] == 12345
    finally:
        set_device_state_watcher_loop_service(None)


def test_voice_scene_silent_alias_is_path_only_and_suppresses_speaker(monkeypatch):
    enqueued = {}

    def fake_enqueue_scene_trigger(payload):
        enqueued["payload"] = payload
        return {
            "run_id": "scene_silent_outfit_suggest_001",
            "intent": payload.intent,
            "action": "accepted",
            "async_mode": True,
            "status": "accepted",
            "status_endpoint": "/api/voice/scene-runs/scene_silent_outfit_suggest_001",
        }

    monkeypatch.setenv("MILOCO_LIFE_XIAOMI_SPEAKER_ID", "speaker_env_01")
    monkeypatch.setenv("MILOCO_LIFE_CAMERA_ID", "camera_env_01")
    monkeypatch.setattr(
        "miloco.voice.router.enqueue_life_scene_trigger_service",
        fake_enqueue_scene_trigger,
    )

    response = _voice_client().get("/api/voice/scene-silent/outfit-suggest")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "accepted"
    assert body["data"]["intent"] == "outfit_suggest"
    payload = enqueued["payload"]
    assert payload.intent == "outfit_suggest"
    assert payload.speaker_id == "speaker_env_01"
    assert payload.camera_id is None
    assert payload.suppress_speaker is True


def test_voice_scene_silent_visual_alias_keeps_camera_but_suppresses_speaker(
    monkeypatch,
):
    enqueued = {}

    def fake_enqueue_scene_trigger(payload):
        enqueued["payload"] = payload
        return {
            "run_id": "scene_silent_outfit_check_001",
            "intent": payload.intent,
            "action": "accepted",
            "async_mode": True,
            "status": "accepted",
            "status_endpoint": "/api/voice/scene-runs/scene_silent_outfit_check_001",
        }

    monkeypatch.setenv("MILOCO_LIFE_XIAOMI_SPEAKER_ID", "speaker_env_01")
    monkeypatch.setenv("MILOCO_LIFE_CAMERA_ID", "camera_env_01")
    monkeypatch.setattr(
        "miloco.voice.router.enqueue_life_scene_trigger_service",
        fake_enqueue_scene_trigger,
    )

    response = _voice_client().get("/api/voice/scene-silent/outfit-check")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "accepted"
    assert body["data"]["intent"] == "outfit_check"
    payload = enqueued["payload"]
    assert payload.intent == "outfit_check"
    assert payload.speaker_id == "speaker_env_01"
    assert payload.camera_id == "camera_env_01"
    assert payload.suppress_speaker is True


def test_voice_scene_trigger_post_can_enqueue_async(monkeypatch):
    enqueued = {}

    def fake_enqueue_scene_trigger(payload):
        enqueued["payload"] = payload
        return {
            "run_id": "scene_async_post_001",
            "intent": payload.intent,
            "action": "accepted",
            "async_mode": True,
            "status": "accepted",
            "status_endpoint": "/api/voice/scene-runs/scene_async_post_001",
        }

    run_scene_trigger = AsyncMock()
    monkeypatch.setattr(
        "miloco.voice.router.enqueue_life_scene_trigger_service",
        fake_enqueue_scene_trigger,
    )
    monkeypatch.setattr(
        "miloco.voice.router.run_life_scene_trigger_service", run_scene_trigger
    )

    response = _voice_client().post(
        "/api/voice/scene-trigger",
        json={
            "intent": "cooking_check",
            "speaker_id": "speaker_01",
            "camera_id": "camera_01",
            "suppress_speaker": True,
            "async_mode": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["action"] == "accepted"
    assert body["data"]["run_id"] == "scene_async_post_001"
    assert (
        body["data"]["status_endpoint"] == "/api/voice/scene-runs/scene_async_post_001"
    )
    assert enqueued["payload"].intent == "cooking_check"
    run_scene_trigger.assert_not_awaited()


async def test_enqueue_scene_trigger_records_completed_run_status():
    from miloco.life.scene_trigger import LifeSceneTriggerPayload
    from miloco.life.voice_session import clear_life_voice_sessions
    from miloco.voice.router import (
        clear_life_scene_trigger_runs,
        enqueue_life_scene_trigger_service,
        get_life_scene_trigger_run_service,
    )

    clear_life_voice_sessions()
    clear_life_scene_trigger_runs()

    accepted = enqueue_life_scene_trigger_service(
        LifeSceneTriggerPayload(intent="outfit_suggest", suppress_speaker=True)
    )

    run_id = str(accepted["run_id"])
    initial = get_life_scene_trigger_run_service(run_id)
    assert initial is not None
    assert initial["run_id"] == run_id
    assert initial["status"] in {"accepted", "running", "completed"}
    assert initial["status_endpoint"] == f"/api/voice/scene-runs/{run_id}"

    completed = initial
    for _ in range(20):
        completed = get_life_scene_trigger_run_service(run_id)
        if completed and completed["status"] == "completed":
            break
        await asyncio.sleep(0.01)

    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["result"]["intent"] == "outfit_suggest"
    assert completed["result"]["visual_capture"] is None


def test_voice_scene_run_status_endpoint_returns_record(monkeypatch):
    def fake_get_run(run_id: str):
        return {
            "run_id": run_id,
            "intent": "outfit_suggest",
            "status": "completed",
            "async_mode": True,
            "status_endpoint": f"/api/voice/scene-runs/{run_id}",
            "result": {"action": "responded"},
            "error": None,
        }

    monkeypatch.setattr(
        "miloco.voice.router.get_life_scene_trigger_run_service", fake_get_run
    )

    response = _voice_client().get("/api/voice/scene-runs/run_001")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["run_id"] == "run_001"
    assert body["data"]["status"] == "completed"


def test_voice_scene_run_status_endpoint_returns_404_for_unknown_run():
    response = _voice_client().get("/api/voice/scene-runs/missing_run")

    assert response.status_code == 404


async def test_latest_scene_run_status_endpoint_returns_newest_run():
    from miloco.life.scene_trigger import LifeSceneTriggerPayload
    from miloco.voice.router import (
        clear_life_scene_trigger_runs,
        enqueue_life_scene_trigger_service,
    )

    clear_life_scene_trigger_runs()
    first = enqueue_life_scene_trigger_service(
        LifeSceneTriggerPayload(intent="cooking_suggest", suppress_speaker=True)
    )
    second = enqueue_life_scene_trigger_service(
        LifeSceneTriggerPayload(intent="outfit_suggest", suppress_speaker=True)
    )
    await asyncio.sleep(0.05)

    response = _voice_client().get("/api/voice/scene-runs/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["run_id"] == second["run_id"]
    assert body["data"]["intent"] == "outfit_suggest"
    assert body["data"]["run_id"] != first["run_id"]


async def test_scene_trigger_explicit_intent_does_not_reuse_other_domain_session(
    monkeypatch,
):
    from miloco.life.scene_trigger import (
        LifeSceneTriggerPayload,
        run_life_scene_trigger,
    )
    from miloco.life.voice_session import clear_life_voice_sessions

    clear_life_voice_sessions()
    speaker_play = AsyncMock(return_value={"delivered": False, "reason": "suppressed"})
    monkeypatch.setattr(
        "miloco.life.scene_trigger.play_xiaomi_speaker_message", speaker_play
    )

    await run_life_scene_trigger(
        LifeSceneTriggerPayload(
            intent="cooking_suggest",
            speaker_id="speaker_01",
            suppress_speaker=True,
        )
    )
    result = await run_life_scene_trigger(
        LifeSceneTriggerPayload(
            intent="outfit_suggest",
            speaker_id="speaker_01",
            suppress_speaker=True,
        )
    )

    assert result["intent"] == "outfit_suggest"
    assert result["first"]["domain"] == "outfit"
    assert result["first"]["used_last_context"] is False
