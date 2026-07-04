# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Tests for short-lived camera microphone voice listening."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from miloco.life.router import router
from miloco.life.voice_session import clear_life_voice_sessions

OUTFIT_COMMAND = "\u5e2e\u6211\u770b\u770b\u8fd9\u4ef6\u8863\u670d\u600e\u4e48\u642d"
UNRELATED_COMMAND = "\u4eca\u5929\u5929\u6c14\u600e\u4e48\u6837"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_camera_voice_listen_transcript_triggers_agent_and_speaker(
    monkeypatch,
    tmp_path,
):
    clear_life_voice_sessions()
    playback = AsyncMock(return_value={"delivered": True, "did": "2119430286"})
    capture = AsyncMock()
    transcribe = AsyncMock()
    monkeypatch.setattr(
        "miloco.life.camera_voice.play_xiaomi_speaker_request", playback
    )
    monkeypatch.setattr("miloco.life.camera_voice.capture_camera_voice_window", capture)
    monkeypatch.setattr(
        "miloco.life.camera_voice.transcribe_camera_voice_audio", transcribe
    )

    response = _client().post(
        "/api/life/camera-voice-listen",
        json={
            "camera_id": "1182348802",
            "speaker_id": "2119430286",
            "transcript": OUTFIT_COMMAND,
            "mimo_payload": {
                "source_id": "camera_voice_fixture",
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
            "db_path": str(tmp_path / "camera-voice.db"),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["matched"] is True
    assert data["source"] == "provided_transcript"
    assert data["domain"] == "outfit"
    assert data["capture"]["skipped"] is True
    assert data["first"]["action"] == "awaiting_visual_capture"
    assert data["final"]["action"] == "responded"
    assert data["final"]["speaker_request"]["preferred_device_id"] == "2119430286"
    assert data["playback"] == {"delivered": True, "did": "2119430286"}
    capture.assert_not_awaited()
    transcribe.assert_not_awaited()
    playback.assert_awaited_once()


def test_camera_voice_listen_ignores_unrelated_transcript_without_speaker(
    monkeypatch,
    tmp_path,
):
    clear_life_voice_sessions()
    playback = AsyncMock()
    capture = AsyncMock()
    monkeypatch.setattr(
        "miloco.life.camera_voice.play_xiaomi_speaker_request", playback
    )
    monkeypatch.setattr("miloco.life.camera_voice.capture_camera_voice_window", capture)

    response = _client().post(
        "/api/life/camera-voice-listen",
        json={
            "camera_id": "1182348802",
            "speaker_id": "2119430286",
            "transcript": UNRELATED_COMMAND,
            "db_path": str(tmp_path / "camera-voice-unrelated.db"),
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["matched"] is False
    assert data["domain"] is None
    assert data["capture"]["skipped"] is True
    assert data["first"]["action"] == "ignored"
    assert data["final"]["action"] == "ignored"
    assert data["playback"] is None
    capture.assert_not_awaited()
    playback.assert_not_awaited()


async def test_camera_voice_listen_captures_and_transcribes_when_no_transcript(
    monkeypatch,
    tmp_path,
):
    from miloco.life.camera_voice import (
        CameraVoiceListenPayload,
        CameraVoiceWindow,
        run_camera_voice_listen,
    )

    clear_life_voice_sessions()
    capture = AsyncMock(
        return_value=CameraVoiceWindow(
            camera_id="1182348802",
            channel=0,
            requested_duration_ms=3000,
            audio_base64="ZmFrZSBhdWRpbw==",
            clip_base64="ZmFrZSB2aWRlbw==",
            audio_bytes=10,
            clip_bytes=10,
        )
    )
    transcribe = AsyncMock(return_value=OUTFIT_COMMAND)
    playback = AsyncMock(return_value={"delivered": True})
    monkeypatch.setattr("miloco.life.camera_voice.capture_camera_voice_window", capture)
    monkeypatch.setattr(
        "miloco.life.camera_voice.transcribe_camera_voice_audio", transcribe
    )
    monkeypatch.setattr(
        "miloco.life.camera_voice.play_xiaomi_speaker_request", playback
    )

    result = await run_camera_voice_listen(
        CameraVoiceListenPayload(
            camera_id="1182348802",
            speaker_id="2119430286",
            listen_duration_ms=3000,
            mimo_payload={
                "source_id": "camera_voice_live_fixture",
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
            occasion="video meeting",
            weather="indoor",
            persist=False,
            db_path=str(tmp_path / "camera-voice-live.db"),
        )
    )

    assert result["source"] == "camera_audio"
    assert result["transcript"] == OUTFIT_COMMAND
    assert result["matched"] is True
    assert result["capture"]["audio_bytes"] == 10
    assert result["capture"]["clip_bytes"] == 10
    assert result["final"]["action"] == "responded"
    capture.assert_awaited_once()
    transcribe.assert_awaited_once_with(
        "ZmFrZSBhdWRpbw==",
        prompt="Transcribe the user's Chinese speech command from the camera microphone.",
    )
    playback.assert_awaited_once()


async def test_camera_voice_listen_separates_asr_audio_from_visual_capture(
    monkeypatch,
    tmp_path,
):
    from miloco.life.camera_voice import (
        CameraVoiceListenPayload,
        CameraVoiceWindow,
        run_camera_voice_listen,
    )

    clear_life_voice_sessions()
    capture = AsyncMock(
        side_effect=[
            CameraVoiceWindow(
                camera_id="1182348802",
                channel=0,
                requested_duration_ms=3000,
                audio_base64="ZmFrZSBhdWRpbw==",
                audio_bytes=10,
            ),
            CameraVoiceWindow(
                camera_id="1182348802",
                channel=0,
                requested_duration_ms=2000,
                clip_base64="ZmFrZSB2aXN1YWw=",
                clip_bytes=11,
            ),
        ]
    )
    transcribe = AsyncMock(return_value=OUTFIT_COMMAND)
    voice_command = AsyncMock(
        side_effect=[
            {
                "matched": True,
                "session_id": "life_voice_test",
                "domain": "outfit",
                "action": "awaiting_visual_capture",
                "needs_visual_capture": True,
            },
            {
                "matched": True,
                "session_id": "life_voice_test",
                "domain": "outfit",
                "action": "responded",
                "needs_visual_capture": False,
                "speaker_request": {
                    "preferred_device_id": "2119430286",
                    "message": "outfit advice",
                },
            },
        ]
    )
    playback = AsyncMock(return_value={"delivered": True})
    monkeypatch.setattr("miloco.life.camera_voice.capture_camera_voice_window", capture)
    monkeypatch.setattr(
        "miloco.life.camera_voice.transcribe_camera_voice_audio", transcribe
    )
    monkeypatch.setattr(
        "miloco.life.camera_voice.run_life_voice_command", voice_command
    )
    monkeypatch.setattr(
        "miloco.life.camera_voice.play_xiaomi_speaker_request", playback
    )

    result = await run_camera_voice_listen(
        CameraVoiceListenPayload(
            camera_id="1182348802",
            speaker_id="2119430286",
            listen_duration_ms=3000,
            camera_duration_ms=2000,
            occasion="video meeting",
            weather="indoor",
            persist=False,
            db_path=str(tmp_path / "camera-voice-audio-then-visual.db"),
        )
    )

    assert result["source"] == "camera_audio"
    assert result["capture"]["audio_bytes"] == 10
    assert result["capture"]["clip_bytes"] == 11
    assert result["final"]["action"] == "responded"
    assert capture.await_args_list[0].kwargs == {
        "camera_id": "1182348802",
        "channel": 0,
        "duration_ms": 3000,
        "include_audio": True,
        "include_clip": False,
    }
    assert capture.await_args_list[1].kwargs == {
        "camera_id": "1182348802",
        "channel": 0,
        "duration_ms": 2000,
        "include_audio": False,
        "include_clip": True,
    }
    transcribe.assert_awaited_once_with(
        "ZmFrZSBhdWRpbw==",
        prompt="Transcribe the user's Chinese speech command from the camera microphone.",
    )
    playback.assert_awaited_once()


async def test_camera_voice_listen_returns_structured_asr_failure(
    monkeypatch,
    tmp_path,
):
    from miloco.life.camera_voice import (
        CameraVoiceListenPayload,
        CameraVoiceWindow,
        run_camera_voice_listen,
    )
    from miloco.perception.engine.omni.omni_client import OmniError

    clear_life_voice_sessions()
    capture = AsyncMock(
        return_value=CameraVoiceWindow(
            camera_id="1182348802",
            channel=0,
            requested_duration_ms=3000,
            audio_base64="ZmFrZSBhdWRpbw==",
            clip_base64="ZmFrZSB2aWRlbw==",
            audio_bytes=10,
            clip_bytes=10,
        )
    )
    transcribe = AsyncMock(
        side_effect=OmniError("call_life_mimo_chat failed: HTTPStatusError: 401")
    )
    voice_command = AsyncMock()
    playback = AsyncMock()
    monkeypatch.setattr("miloco.life.camera_voice.capture_camera_voice_window", capture)
    monkeypatch.setattr(
        "miloco.life.camera_voice.transcribe_camera_voice_audio", transcribe
    )
    monkeypatch.setattr(
        "miloco.life.camera_voice.run_life_voice_command", voice_command
    )
    monkeypatch.setattr(
        "miloco.life.camera_voice.play_xiaomi_speaker_request", playback
    )

    result = await run_camera_voice_listen(
        CameraVoiceListenPayload(
            camera_id="1182348802",
            speaker_id="2119430286",
            listen_duration_ms=3000,
            life_mimo_base_url="https://token-plan-cn.xiaomimimo.com/v1",
            persist=False,
            db_path=str(tmp_path / "camera-voice-asr-failure.db"),
        )
    )

    assert result["matched"] is False
    assert result["source"] == "camera_audio"
    assert result["transcript"] == ""
    assert result["capture"]["audio_bytes"] == 10
    assert result["capture"]["clip_bytes"] == 10
    assert result["final"]["action"] == "failed"
    assert result["final"]["reason"] == "asr_error"
    assert "401" in result["final"]["error"]
    assert result["final"]["diagnostics"]["life_mimo"] == {
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "asr_model": "mimo-v2.5-asr",
        "vision_model": "mimo-v2.5",
        "task": "asr",
    }
    assert result["session"] == {
        "session_id": None,
        "session_active": False,
        "turn_count": 0,
        "used_last_context": False,
        "context_cache": None,
    }
    assert result["playback"] is None
    voice_command.assert_not_awaited()
    playback.assert_not_awaited()


async def test_camera_voice_listen_transcript_captures_visual_when_needed(
    monkeypatch,
    tmp_path,
):
    from miloco.life.camera_voice import (
        CameraVoiceListenPayload,
        CameraVoiceWindow,
        run_camera_voice_listen,
    )

    clear_life_voice_sessions()
    capture = AsyncMock(
        return_value=CameraVoiceWindow(
            camera_id="1182348802",
            channel=0,
            requested_duration_ms=2000,
            clip_base64="ZmFrZSB2aXN1YWw=",
            clip_bytes=11,
        )
    )
    transcribe = AsyncMock()
    voice_command = AsyncMock(
        side_effect=[
            {
                "matched": True,
                "session_id": "life_voice_test",
                "domain": "outfit",
                "action": "awaiting_visual_capture",
                "needs_visual_capture": True,
            },
            {
                "matched": True,
                "session_id": "life_voice_test",
                "domain": "outfit",
                "action": "responded",
                "needs_visual_capture": False,
                "speaker_request": {
                    "preferred_device_id": "2119430286",
                    "message": "outfit advice",
                },
            },
        ]
    )
    playback = AsyncMock(return_value={"delivered": True})
    monkeypatch.setattr("miloco.life.camera_voice.capture_camera_voice_window", capture)
    monkeypatch.setattr(
        "miloco.life.camera_voice.transcribe_camera_voice_audio", transcribe
    )
    monkeypatch.setattr(
        "miloco.life.camera_voice.run_life_voice_command", voice_command
    )
    monkeypatch.setattr(
        "miloco.life.camera_voice.play_xiaomi_speaker_request", playback
    )

    result = await run_camera_voice_listen(
        CameraVoiceListenPayload(
            camera_id="1182348802",
            speaker_id="2119430286",
            transcript=OUTFIT_COMMAND,
            camera_duration_ms=2000,
            persist=False,
            db_path=str(tmp_path / "camera-voice-transcript-visual.db"),
        )
    )

    assert result["source"] == "provided_transcript"
    assert result["capture"]["skipped"] is False
    assert result["capture"]["clip_bytes"] == 11
    assert result["final"]["action"] == "responded"
    capture.assert_awaited_once_with(
        camera_id="1182348802",
        channel=0,
        duration_ms=2000,
        include_audio=False,
        include_clip=True,
    )
    transcribe.assert_not_awaited()
    second_payload = voice_command.await_args_list[1].args[0]
    assert second_payload.session_id == "life_voice_test"
    assert second_payload.clip_base64 == "ZmFrZSB2aXN1YWw="
    assert second_payload.mimo_payload is None
    assert second_payload.source_id.startswith("provided_transcript_1182348802_")
    playback.assert_awaited_once()


async def test_camera_voice_listen_returns_speaker_failure_diagnostics(
    monkeypatch,
    tmp_path,
):
    from miloco.life.camera_voice import (
        CameraVoiceListenPayload,
        run_camera_voice_listen,
    )

    clear_life_voice_sessions()
    capture = AsyncMock()
    voice_command = AsyncMock(
        return_value={
            "matched": True,
            "session_id": "life_voice_test",
            "domain": "outfit",
            "action": "responded",
            "needs_visual_capture": False,
            "speaker_request": {
                "preferred_device_id": "2119430286",
                "message": "outfit advice",
            },
            "broadcast_text": "outfit advice",
        }
    )
    playback = AsyncMock(side_effect=RuntimeError("speaker control timed out"))
    monkeypatch.setattr("miloco.life.camera_voice.capture_camera_voice_window", capture)
    monkeypatch.setattr(
        "miloco.life.camera_voice.run_life_voice_command", voice_command
    )
    monkeypatch.setattr(
        "miloco.life.camera_voice.play_xiaomi_speaker_request", playback
    )

    result = await run_camera_voice_listen(
        CameraVoiceListenPayload(
            camera_id="1182348802",
            speaker_id="2119430286",
            transcript=OUTFIT_COMMAND,
            persist=False,
            db_path=str(tmp_path / "camera-voice-speaker-failure.db"),
        )
    )

    assert result["matched"] is True
    assert result["final"]["action"] == "responded"
    assert result["final"]["speaker_request"]["preferred_device_id"] == "2119430286"
    assert result["playback"] == {
        "delivered": False,
        "did": "2119430286",
        "action": None,
        "control_result": None,
        "error": "speaker control timed out",
        "reason": "speaker_playback_error",
    }
    capture.assert_not_awaited()
    voice_command.assert_awaited_once()
    playback.assert_awaited_once()


async def test_camera_voice_listen_returns_session_summary_for_followups(
    monkeypatch,
    tmp_path,
):
    from miloco.life.camera_voice import (
        CameraVoiceListenPayload,
        run_camera_voice_listen,
    )

    clear_life_voice_sessions()
    capture = AsyncMock()
    voice_command = AsyncMock(
        return_value={
            "matched": True,
            "session_id": "life_voice_test",
            "session_active": True,
            "domain": "outfit",
            "action": "responded",
            "needs_visual_capture": False,
            "used_last_context": True,
            "turn_count": 2,
            "context_cache": {
                "hit": True,
                "domain": "outfit",
                "source_type": "visual_result",
                "source_id": "voice_check_this_shirt",
                "refresh_reason": None,
            },
            "speaker_request": {
                "preferred_device_id": "2119430286",
                "message": "outfit advice",
            },
            "broadcast_text": "outfit advice",
        }
    )
    playback = AsyncMock(return_value={"delivered": True})
    monkeypatch.setattr("miloco.life.camera_voice.capture_camera_voice_window", capture)
    monkeypatch.setattr(
        "miloco.life.camera_voice.run_life_voice_command", voice_command
    )
    monkeypatch.setattr(
        "miloco.life.camera_voice.play_xiaomi_speaker_request", playback
    )

    result = await run_camera_voice_listen(
        CameraVoiceListenPayload(
            camera_id="1182348802",
            speaker_id="2119430286",
            transcript="follow up outfit command",
            session_id="life_voice_test",
            persist=False,
            db_path=str(tmp_path / "camera-voice-session-summary.db"),
        )
    )

    assert result["session"] == {
        "session_id": "life_voice_test",
        "session_active": True,
        "turn_count": 2,
        "used_last_context": True,
        "context_cache": {
            "hit": True,
            "domain": "outfit",
            "source_type": "visual_result",
            "source_id": "voice_check_this_shirt",
            "refresh_reason": None,
        },
    }
    capture.assert_not_awaited()
    voice_command.assert_awaited_once()
    playback.assert_awaited_once()


async def test_camera_voice_listen_can_force_fresh_visual_session(
    monkeypatch,
    tmp_path,
):
    from miloco.life.camera_voice import (
        CameraVoiceListenPayload,
        CameraVoiceWindow,
        run_camera_voice_listen,
    )

    clear_life_voice_sessions()
    capture = AsyncMock(
        return_value=CameraVoiceWindow(
            camera_id="1182348802",
            channel=0,
            requested_duration_ms=2000,
            clip_base64="ZmFrZSB2aXN1YWw=",
            clip_bytes=11,
        )
    )
    voice_command = AsyncMock(
        side_effect=[
            {
                "matched": True,
                "session_id": "life_voice_fresh",
                "session_active": True,
                "domain": "outfit",
                "action": "awaiting_visual_capture",
                "needs_visual_capture": True,
                "used_last_context": False,
                "context_cache": {
                    "hit": False,
                    "source_type": "camera_required",
                    "refresh_reason": "forced_visual_capture",
                },
            },
            {
                "matched": True,
                "session_id": "life_voice_fresh",
                "session_active": True,
                "domain": "outfit",
                "action": "responded",
                "needs_visual_capture": False,
                "used_last_context": False,
                "turn_count": 1,
                "context_cache": {
                    "hit": False,
                    "source_type": "visual_result",
                    "source_id": "camera_audio_1182348802_123",
                    "refresh_reason": "visual_input",
                },
                "speaker_request": {
                    "preferred_device_id": "2119430286",
                    "message": "outfit advice",
                },
                "broadcast_text": "outfit advice",
            },
        ]
    )
    playback = AsyncMock()
    monkeypatch.setattr("miloco.life.camera_voice.capture_camera_voice_window", capture)
    monkeypatch.setattr(
        "miloco.life.camera_voice.run_life_voice_command", voice_command
    )
    monkeypatch.setattr(
        "miloco.life.camera_voice.play_xiaomi_speaker_request", playback
    )

    result = await run_camera_voice_listen(
        CameraVoiceListenPayload(
            camera_id="1182348802",
            speaker_id="2119430286",
            transcript=OUTFIT_COMMAND,
            camera_duration_ms=2000,
            fresh_session=True,
            force_visual_capture=True,
            speak=False,
            persist=False,
            db_path=str(tmp_path / "camera-voice-fresh-visual.db"),
        )
    )

    assert result["source"] == "provided_transcript"
    assert result["capture"]["clip_bytes"] == 11
    assert result["first"]["action"] == "awaiting_visual_capture"
    assert result["first"]["context_cache"]["refresh_reason"] == "forced_visual_capture"
    assert result["final"]["action"] == "responded"
    assert result["session"]["session_id"] == "life_voice_fresh"
    assert result["session"]["used_last_context"] is False
    first_payload = voice_command.await_args_list[0].args[0]
    final_payload = voice_command.await_args_list[1].args[0]
    assert first_payload.fresh_session is True
    assert first_payload.force_visual_capture is True
    assert final_payload.session_id == "life_voice_fresh"
    assert final_payload.clip_base64 == "ZmFrZSB2aXN1YWw="
    capture.assert_awaited_once_with(
        camera_id="1182348802",
        channel=0,
        duration_ms=2000,
        include_audio=False,
        include_clip=True,
    )
    playback.assert_not_awaited()


async def test_camera_voice_listen_returns_structured_mimo_failure(
    monkeypatch,
    tmp_path,
):
    from miloco.life.camera_voice import (
        CameraVoiceListenPayload,
        CameraVoiceWindow,
        run_camera_voice_listen,
    )
    from miloco.perception.engine.omni.omni_client import OmniError

    clear_life_voice_sessions()
    capture = AsyncMock(
        return_value=CameraVoiceWindow(
            camera_id="1182348802",
            channel=0,
            requested_duration_ms=2000,
            clip_base64="ZmFrZSB2aXN1YWw=",
            clip_bytes=11,
        )
    )
    voice_command = AsyncMock(
        side_effect=[
            {
                "matched": True,
                "session_id": "life_voice_test",
                "domain": "outfit",
                "action": "awaiting_visual_capture",
                "needs_visual_capture": True,
            },
            OmniError("call_life_mimo_chat failed: HTTPStatusError: 401"),
        ]
    )
    playback = AsyncMock()
    monkeypatch.setattr("miloco.life.camera_voice.capture_camera_voice_window", capture)
    monkeypatch.setattr(
        "miloco.life.camera_voice.run_life_voice_command", voice_command
    )
    monkeypatch.setattr(
        "miloco.life.camera_voice.play_xiaomi_speaker_request", playback
    )

    result = await run_camera_voice_listen(
        CameraVoiceListenPayload(
            camera_id="1182348802",
            speaker_id="2119430286",
            transcript=OUTFIT_COMMAND,
            camera_duration_ms=2000,
            life_mimo_base_url="https://token-plan-cn.xiaomimimo.com/v1",
            persist=False,
            db_path=str(tmp_path / "camera-voice-mimo-failure.db"),
        )
    )

    assert result["matched"] is True
    assert result["capture"]["clip_bytes"] == 11
    assert result["final"]["action"] == "failed"
    assert result["final"]["reason"] == "mimo_error"
    assert "401" in result["final"]["error"]
    assert result["final"]["diagnostics"]["life_mimo"] == {
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "asr_model": "mimo-v2.5-asr",
        "vision_model": "mimo-v2.5",
        "task": "vision",
    }
    assert result["playback"] is None
    playback.assert_not_awaited()


async def test_camera_voice_listen_returns_structured_first_turn_failure(
    monkeypatch,
    tmp_path,
):
    from miloco.life.camera_voice import (
        CameraVoiceListenPayload,
        run_camera_voice_listen,
    )
    from miloco.perception.engine.omni.omni_client import OmniError

    clear_life_voice_sessions()
    capture = AsyncMock()
    voice_command = AsyncMock(
        side_effect=OmniError("Life voice command failed before visual capture")
    )
    playback = AsyncMock()
    monkeypatch.setattr("miloco.life.camera_voice.capture_camera_voice_window", capture)
    monkeypatch.setattr(
        "miloco.life.camera_voice.run_life_voice_command", voice_command
    )
    monkeypatch.setattr(
        "miloco.life.camera_voice.play_xiaomi_speaker_request", playback
    )

    result = await run_camera_voice_listen(
        CameraVoiceListenPayload(
            camera_id="1182348802",
            speaker_id="2119430286",
            transcript=OUTFIT_COMMAND,
            persist=False,
            db_path=str(tmp_path / "camera-voice-first-turn-failure.db"),
        )
    )

    assert result["matched"] is False
    assert result["source"] == "provided_transcript"
    assert result["transcript"] == OUTFIT_COMMAND
    assert result["capture"]["skipped"] is True
    assert result["first"]["action"] == "failed"
    assert result["first"]["reason"] == "life_voice_error"
    assert result["final"]["action"] == "failed"
    assert result["final"]["speaker_request"] is None
    assert "before visual capture" in result["final"]["error"]
    assert result["playback"] is None
    capture.assert_not_awaited()
    voice_command.assert_awaited_once()
    playback.assert_not_awaited()


async def test_camera_voice_listen_wraps_non_json_mimo_response(
    monkeypatch,
    tmp_path,
):
    from miloco.life.camera_voice import (
        CameraVoiceListenPayload,
        CameraVoiceWindow,
        run_camera_voice_listen,
    )
    from miloco.perception.engine.omni.omni_client import OmniError

    clear_life_voice_sessions()
    capture = AsyncMock(
        return_value=CameraVoiceWindow(
            camera_id="1182348802",
            channel=0,
            requested_duration_ms=2000,
            clip_base64="ZmFrZSB2aXN1YWw=",
            clip_bytes=11,
        )
    )
    first = {
        "matched": True,
        "session_id": "life_voice_test",
        "domain": "outfit",
        "action": "awaiting_visual_capture",
        "needs_visual_capture": True,
    }

    async def fake_voice_command(payload):
        if payload.clip_base64:
            raise OmniError("Live MiMo response was not valid JSON")
        return first

    monkeypatch.setattr("miloco.life.camera_voice.capture_camera_voice_window", capture)
    monkeypatch.setattr(
        "miloco.life.camera_voice.run_life_voice_command", fake_voice_command
    )

    result = await run_camera_voice_listen(
        CameraVoiceListenPayload(
            camera_id="1182348802",
            speaker_id="2119430286",
            transcript=OUTFIT_COMMAND,
            camera_duration_ms=2000,
            persist=False,
            db_path=str(tmp_path / "camera-voice-non-json.db"),
        )
    )

    assert result["final"]["action"] == "failed"
    assert result["final"]["reason"] == "mimo_error"
    assert "not valid JSON" in result["final"]["error"]
