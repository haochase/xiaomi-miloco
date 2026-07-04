# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""XiaoAi/MiHome scene trigger orchestration for on-demand life agents."""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from miloco.life.intent import infer_life_occasion
from miloco.life.resource_lease import ResourceLeaseManager
from miloco.life.service import LifeTriggerSource
from miloco.life.voice_bridge import (
    play_xiaomi_speaker_message,
    record_life_camera_clip,
)
from miloco.life.voice_session import (
    DEFAULT_CAMERA_CHANNEL,
    DEFAULT_CAMERA_DURATION_MS,
    run_life_voice_command,
)

LifeSceneIntent = Literal[
    "outfit_check",
    "outfit_suggest",
    "cooking_check",
    "cooking_suggest",
]


@dataclass(frozen=True)
class _SceneIntentSpec:
    text: str
    ack_message: str
    prompt: str
    occasion: str
    people_count: int
    time_budget_minutes: int


_SCENE_INTENTS: dict[LifeSceneIntent, _SceneIntentSpec] = {
    "outfit_check": _SceneIntentSpec(
        text="\u5e2e\u6211\u770b\u770b\u8fd9\u4ef6\u8863\u670d\u600e\u4e48\u642d",
        ack_message="\u597d\u7684\uff0c\u6211\u770b\u4e00\u4e0b\u3002",
        prompt=(
            "Focus on visible clothing, shoes, accessories, worn outfit, "
            "uncertain items, and conservative outfit advice. Reply in simplified "
            "Chinese and avoid English clothing words unless they are brand names."
        ),
        occasion="\u65e5\u5e38\u51fa\u95e8",
        people_count=1,
        time_budget_minutes=20,
    ),
    "outfit_suggest": _SceneIntentSpec(
        text="\u4eca\u5929\u7a7f\u4ec0\u4e48",
        ack_message="\u597d\u7684\uff0c\u6211\u6574\u7406\u4e00\u4e0b\u7a7f\u642d\u5efa\u8bae\u3002",
        prompt=(
            "Use stored wardrobe items and current context. Reply in simplified "
            "Chinese with a short practical outfit suggestion."
        ),
        occasion="\u4eca\u5929\u51fa\u95e8",
        people_count=1,
        time_budget_minutes=20,
    ),
    "cooking_check": _SceneIntentSpec(
        text="\u5e2e\u6211\u770b\u770b\u51b0\u7bb1\u548c\u53a8\u623f\u91cc\u6709\u4ec0\u4e48\u98df\u6750",
        ack_message="\u597d\u7684\uff0c\u6211\u770b\u4e00\u4e0b\u53a8\u623f\u548c\u98df\u6750\u3002",
        prompt=(
            "Focus on visible ingredients, fridge items, kitchen tools, cooking "
            "state, uncertainty, and conservative safety-aware cooking advice. "
            "Reply in simplified Chinese."
        ),
        occasion="\u4eca\u5929\u505a\u996d",
        people_count=2,
        time_budget_minutes=30,
    ),
    "cooking_suggest": _SceneIntentSpec(
        text="\u4eca\u5929\u5403\u4ec0\u4e48",
        ack_message="\u597d\u7684\uff0c\u6211\u6574\u7406\u4e00\u4e0b\u505a\u996d\u5efa\u8bae\u3002",
        prompt=(
            "Use stored pantry items, time budget, people count, weather, and "
            "recent context. Reply in simplified Chinese with a practical cooking "
            "suggestion."
        ),
        occasion="\u4eca\u5929\u505a\u996d",
        people_count=2,
        time_budget_minutes=30,
    ),
}

_RESOURCE_LEASE_MANAGER = ResourceLeaseManager()


@dataclass(frozen=True)
class LifeSceneTriggerPayload:
    """Input accepted from a XiaoAi/MiHome scene or a local scene simulator."""

    intent: LifeSceneIntent
    text: str | None = None
    session_id: str | None = None
    speaker_id: str | None = None
    camera_id: str | None = None
    camera_channel: int = DEFAULT_CAMERA_CHANNEL
    camera_duration_ms: int = DEFAULT_CAMERA_DURATION_MS
    trigger_source: LifeTriggerSource = "voice_intent"
    source_id: str | None = None
    prompt: str | None = None
    clip_base64: str | None = None
    mimo_payload: dict[str, Any] | str | None = None
    occasion: str | None = None
    weather: str | None = None
    people_count: int | None = None
    time_budget_minutes: int | None = None
    persist: bool = True
    db_path: str | None = None
    ack_message: str | None = None
    suppress_speaker: bool = False


@dataclass(frozen=True)
class _SceneVoicePayload:
    text: str
    session_id: str | None = None
    speaker_id: str | None = None
    camera_id: str | None = None
    camera_channel: int = DEFAULT_CAMERA_CHANNEL
    camera_duration_ms: int = DEFAULT_CAMERA_DURATION_MS
    trigger_source: LifeTriggerSource = "voice_intent"
    source_id: str | None = None
    prompt: str | None = None
    clip_base64: str | None = None
    mimo_payload: dict[str, Any] | str | None = None
    occasion: str = "\u65e5\u5e38\u51fa\u95e8"
    weather: str | None = None
    people_count: int = 1
    time_budget_minutes: int = 20
    persist: bool = True
    db_path: str | None = None


async def run_life_scene_trigger(payload: LifeSceneTriggerPayload) -> dict[str, Any]:
    """Run one XiaoAi scene trigger with immediate ack, optional camera, and speech."""
    spec = _SCENE_INTENTS[payload.intent]
    run_id = f"life_scene_{uuid4().hex}"
    text = (payload.text or spec.text).strip()
    ack_message = (payload.ack_message or spec.ack_message).strip()
    speaker_id = payload.speaker_id
    started_at = time.perf_counter()
    stages: list[dict[str, Any]] = []

    ack_playback = await _time_stage(
        stages,
        started_at,
        "ack_playback",
        _play_scene_message(
            ack_message,
            speaker_id=speaker_id,
            suppress=payload.suppress_speaker,
        ),
    )

    first = await _time_stage(
        stages,
        started_at,
        "agent_initial",
        run_life_voice_command(_voice_payload_from_scene(payload, spec=spec, text=text)),
    )
    final = first
    visual_capture: dict[str, Any] | None = None

    if first.get("needs_visual_capture"):
        camera_request = first.get("camera_request") or {}
        camera_id = str(camera_request.get("camera_id") or payload.camera_id or "")
        if not camera_id:
            final = _camera_missing_response(first)
        else:
            channel = int(camera_request.get("channel", payload.camera_channel))
            duration_ms = int(
                camera_request.get("duration_ms", payload.camera_duration_ms)
            )
            visual_capture_started_at_ms = _elapsed_ms(started_at)
            lease = await _RESOURCE_LEASE_MANAGER.try_acquire("camera", camera_id)
            if not lease.acquired:
                visual_capture_ended_at_ms = _elapsed_ms(started_at)
                visual_capture = _visual_capture_record(
                    camera_id=camera_id,
                    channel=channel,
                    duration_ms=duration_ms,
                    bytes_count=0,
                    release_reason="busy",
                    visual_capture_started_at_ms=visual_capture_started_at_ms,
                    visual_capture_ended_at_ms=visual_capture_ended_at_ms,
                )
                final = _camera_lease_busy_response(first, camera_id)
            else:
                capture_error: Exception | None = None
                clip_bytes = b""
                try:
                    clip_bytes = await _time_stage(
                        stages,
                        started_at,
                        "camera_capture",
                        record_life_camera_clip(
                            camera_id=camera_id,
                            channel=channel,
                            duration_ms=duration_ms,
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    capture_error = exc
                finally:
                    visual_capture_ended_at_ms = _elapsed_ms(started_at)
                    await lease.release(reason="completed")

                if capture_error is not None:
                    visual_capture = _visual_capture_record(
                        camera_id=camera_id,
                        channel=channel,
                        duration_ms=duration_ms,
                        bytes_count=0,
                        release_reason="failed",
                        visual_capture_started_at_ms=visual_capture_started_at_ms,
                        visual_capture_ended_at_ms=visual_capture_ended_at_ms,
                        error=str(capture_error),
                    )
                    final = _camera_capture_failed_response(
                        first,
                        str(capture_error),
                    )
                else:
                    visual_capture = _visual_capture_record(
                        camera_id=camera_id,
                        channel=channel,
                        duration_ms=duration_ms,
                        bytes_count=len(clip_bytes),
                        release_reason="completed",
                        visual_capture_started_at_ms=visual_capture_started_at_ms,
                        visual_capture_ended_at_ms=visual_capture_ended_at_ms,
                    )
                    final = await _time_stage(
                        stages,
                        started_at,
                        "agent_visual",
                        run_life_voice_command(
                            _voice_payload_from_scene(
                                payload,
                                spec=spec,
                                text=text,
                                session_id=str(first.get("session_id") or ""),
                                camera_id=camera_id,
                                camera_channel=channel,
                                camera_duration_ms=duration_ms,
                                source_id=(
                                    payload.source_id
                                    or f"scene_camera_{camera_id}_{int(time.time())}"
                                ),
                                clip_base64=base64.b64encode(clip_bytes).decode(
                                    "ascii"
                                ),
                            )
                        ),
                    )

    final_playback = await _time_stage(
        stages,
        started_at,
        "final_playback",
        _play_final_response(
            final,
            speaker_id=speaker_id,
            suppress=payload.suppress_speaker,
        ),
    )
    first_context_cache = _context_cache(first)
    final_context_cache = _context_cache(final)
    cache_hit = _cache_hit(first_context_cache, final_context_cache)
    visual_refresh_reason = _visual_refresh_reason(
        first_context_cache,
        final_context_cache,
    )

    return {
        "run_id": run_id,
        "intent": payload.intent,
        "text": text,
        "action": final.get("action"),
        "cache_hit": cache_hit,
        "visual_refresh_reason": visual_refresh_reason,
        "first_context_cache": first_context_cache,
        "final_context_cache": final_context_cache,
        "ack": {
            "message": ack_message,
            "playback": ack_playback,
        },
        "first": first,
        "visual_capture": visual_capture,
        "final": final,
        "final_playback": final_playback,
        "timing": _build_timing_summary(
            stages,
            cache_hit=cache_hit,
            visual_refresh_reason=visual_refresh_reason,
        ),
    }


def _voice_payload_from_scene(
    payload: LifeSceneTriggerPayload,
    *,
    spec: _SceneIntentSpec,
    text: str,
    session_id: str | None = None,
    camera_id: str | None = None,
    camera_channel: int | None = None,
    camera_duration_ms: int | None = None,
    source_id: str | None = None,
    clip_base64: str | None = None,
) -> _SceneVoicePayload:
    return _SceneVoicePayload(
        text=text,
        session_id=session_id or payload.session_id,
        speaker_id=payload.speaker_id,
        camera_id=camera_id or payload.camera_id,
        camera_channel=camera_channel or payload.camera_channel,
        camera_duration_ms=camera_duration_ms or payload.camera_duration_ms,
        trigger_source=payload.trigger_source,
        source_id=source_id or payload.source_id,
        prompt=payload.prompt or spec.prompt,
        clip_base64=clip_base64 or payload.clip_base64,
        mimo_payload=payload.mimo_payload,
        occasion=payload.occasion or infer_life_occasion(text, default=spec.occasion),
        weather=payload.weather,
        people_count=payload.people_count or spec.people_count,
        time_budget_minutes=payload.time_budget_minutes or spec.time_budget_minutes,
        persist=payload.persist,
        db_path=payload.db_path,
    )


async def _play_final_response(
    response: dict[str, Any],
    *,
    speaker_id: str | None,
    suppress: bool,
) -> dict[str, Any]:
    speaker_request = response.get("speaker_request")
    if isinstance(speaker_request, dict):
        message = str(speaker_request.get("message") or "")
        preferred = speaker_request.get("preferred_device_id") or speaker_id
        return await _play_scene_message(
            message,
            speaker_id=str(preferred) if preferred else None,
            suppress=suppress,
        )

    fallback = _fallback_message(response)
    if fallback:
        return await _play_scene_message(
            fallback,
            speaker_id=speaker_id,
            suppress=suppress,
        )
    return {"delivered": False, "reason": "no final speaker message"}


async def _play_scene_message(
    message: str,
    *,
    speaker_id: str | None,
    suppress: bool,
) -> dict[str, Any]:
    message = message.strip()
    if not message:
        return {"delivered": False, "reason": "empty message"}
    if suppress:
        return {"delivered": False, "reason": "suppressed", "message": message}
    speaker_resource_id = speaker_id or "auto"
    lease = await _RESOURCE_LEASE_MANAGER.try_acquire(
        "speaker",
        speaker_resource_id,
    )
    if not lease.acquired:
        return {
            "delivered": False,
            "reason": "speaker_lease_busy",
            "speaker_id": speaker_resource_id,
            "message": message,
        }
    try:
        return await play_xiaomi_speaker_message(message, speaker_id)
    finally:
        await lease.release(reason="completed")


def _fallback_message(response: dict[str, Any]) -> str | None:
    if response.get("matched") is False:
        return "\u6211\u8fd8\u6ca1\u6709\u8bc6\u522b\u5230\u53ef\u7528\u7684\u751f\u6d3b\u5efa\u8bae\u610f\u56fe\u3002"
    if response.get("action") == "duplicate_ignored":
        return None
    trigger = response.get("trigger")
    if isinstance(trigger, dict):
        notes = trigger.get("low_confidence_notes")
        if notes:
            return "\u6682\u65f6\u7f3a\u5c11\u8db3\u591f\u4fe1\u606f\uff0c\u5efa\u8bae\u8865\u5145\u8863\u6a71\u6216\u98df\u6750\u4fe1\u606f\u540e\u518d\u8bd5\u3002"
    if response.get("action") == "responded":
        return "\u6682\u65f6\u6ca1\u6709\u8db3\u591f\u4fe1\u606f\u751f\u6210\u660e\u786e\u5efa\u8bae\u3002"
    return None


async def _time_stage(
    stages: list[dict[str, Any]],
    started_at: float,
    stage: str,
    awaitable,
):
    started_ms = _elapsed_ms(started_at)
    try:
        result = await awaitable
    except Exception as exc:
        _append_stage(
            stages,
            stage=stage,
            started_ms=started_ms,
            status="failed",
            error=str(exc),
            started_at=started_at,
        )
        raise
    _append_stage(
        stages,
        stage=stage,
        started_ms=started_ms,
        status="completed",
        error=None,
        started_at=started_at,
    )
    return result


def _append_stage(
    stages: list[dict[str, Any]],
    *,
    stage: str,
    started_ms: int,
    status: Literal["completed", "failed"],
    error: str | None,
    started_at: float,
) -> None:
    ended_ms = _elapsed_ms(started_at)
    item: dict[str, Any] = {
        "stage": stage,
        "started_ms": started_ms,
        "ended_ms": ended_ms,
        "duration_ms": ended_ms - started_ms,
        "status": status,
    }
    if error:
        item["error"] = error
    stages.append(item)


def _build_timing_summary(
    stages: list[dict[str, Any]],
    *,
    cache_hit: bool = False,
    visual_refresh_reason: str | None = None,
) -> dict[str, Any]:
    ack = _find_stage(stages, "ack_playback")
    first_response = _find_stage(stages, "agent_initial")
    camera_capture = _find_stage(stages, "camera_capture")
    final_response = _find_stage(stages, "agent_visual") or first_response
    final_playback = _find_stage(stages, "final_playback")
    return {
        "total_ms": stages[-1]["ended_ms"] if stages else 0,
        "ack_started_ms": stages[0]["started_ms"] if stages else 0,
        "first_response_ready_ms": (
            first_response["ended_ms"] if first_response else None
        ),
        "final_response_ready_ms": (
            final_response["ended_ms"] if final_response else None
        ),
        "final_playback_ready_ms": (
            final_playback["ended_ms"] if final_playback else None
        ),
        "trigger_detect_latency_ms": 0,
        "silence_before_ack_ms": ack["started_ms"] if ack else None,
        "ack_latency_ms": ack["duration_ms"] if ack else None,
        "camera_lease_ms": (
            camera_capture["duration_ms"] if camera_capture else None
        ),
        "mimo_latency_ms": final_response["duration_ms"] if final_response else None,
        "answer_latency_ms": final_response["duration_ms"] if final_response else None,
        "tts_first_audio_ms": (
            final_playback["duration_ms"] if final_playback else None
        ),
        "tts_playback_duration_ms": (
            final_playback["duration_ms"] if final_playback else None
        ),
        "total_turn_latency_ms": stages[-1]["ended_ms"] if stages else 0,
        "cache_hit": cache_hit,
        "visual_refresh_reason": visual_refresh_reason,
        "stages": stages,
    }


def _find_stage(
    stages: list[dict[str, Any]],
    stage: str,
) -> dict[str, Any] | None:
    return next((item for item in stages if item["stage"] == stage), None)


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _visual_capture_record(
    *,
    camera_id: str,
    channel: int,
    duration_ms: int,
    bytes_count: int,
    release_reason: Literal["completed", "failed", "busy"],
    visual_capture_started_at_ms: int,
    visual_capture_ended_at_ms: int,
    error: str | None = None,
) -> dict[str, Any]:
    lease_duration_ms = max(
        0,
        visual_capture_ended_at_ms - visual_capture_started_at_ms,
    )
    record: dict[str, Any] = {
        "camera_id": camera_id,
        "channel": channel,
        "duration_ms": duration_ms,
        "bytes": bytes_count,
        "lease_released": True,
        "release_reason": release_reason,
        "lease_duration_ms": lease_duration_ms,
        "visual_capture_started_at_ms": visual_capture_started_at_ms,
        "visual_capture_ended_at_ms": visual_capture_ended_at_ms,
        "lease": {
            "resource_type": "camera",
            "resource_id": camera_id,
            "channel": channel,
            "duration_ms": duration_ms,
            "released": True,
            "release_reason": release_reason,
            "started_at_ms": visual_capture_started_at_ms,
            "ended_at_ms": visual_capture_ended_at_ms,
            "lease_duration_ms": lease_duration_ms,
        },
    }
    if error:
        record["error"] = error
    return record


def _camera_missing_response(first: dict[str, Any]) -> dict[str, Any]:
    return {
        **first,
        "action": "responded",
        "needs_visual_capture": False,
        "camera_request": None,
        "broadcast_text": "\u9700\u8981\u770b\u753b\u9762\uff0c\u4f46\u6682\u65f6\u6ca1\u6709\u53ef\u7528\u7684\u6444\u50cf\u5934\u3002",
        "speaker_request": {
            "channel": "xiaomi_speaker",
            "preferred_device_id": None,
            "message": "\u9700\u8981\u770b\u753b\u9762\uff0c\u4f46\u6682\u65f6\u6ca1\u6709\u53ef\u7528\u7684\u6444\u50cf\u5934\u3002",
            "requires_ack": False,
        },
        "reason": "Scene trigger required visual capture but no camera id was provided.",
    }


def _camera_capture_failed_response(
    first: dict[str, Any],
    error: str,
) -> dict[str, Any]:
    message = "\u6211\u8fd9\u8fb9\u6682\u65f6\u6ca1\u6709\u53d6\u5230\u6444\u50cf\u5934\u753b\u9762\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002"
    return {
        **first,
        "action": "responded",
        "needs_visual_capture": False,
        "camera_request": None,
        "broadcast_text": message,
        "speaker_request": {
            "channel": "xiaomi_speaker",
            "preferred_device_id": None,
            "message": message,
            "requires_ack": False,
        },
        "reason": "camera_capture_failed",
        "error": error,
    }


def _camera_lease_busy_response(
    first: dict[str, Any],
    camera_id: str,
) -> dict[str, Any]:
    message = "\u6444\u50cf\u5934\u6b63\u5728\u5904\u7406\u53e6\u4e00\u6b21\u89c6\u89c9\u8bf7\u6c42\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002"
    return {
        **first,
        "action": "responded",
        "needs_visual_capture": False,
        "camera_request": None,
        "broadcast_text": message,
        "speaker_request": {
            "channel": "xiaomi_speaker",
            "preferred_device_id": None,
            "message": message,
            "requires_ack": False,
        },
        "reason": "camera_lease_busy",
        "camera_id": camera_id,
    }


def _context_cache(response: dict[str, Any]) -> dict[str, Any] | None:
    context_cache = response.get("context_cache")
    if isinstance(context_cache, dict):
        return context_cache
    return None


def _cache_hit(
    first_context_cache: dict[str, Any] | None,
    final_context_cache: dict[str, Any] | None,
) -> bool:
    if isinstance(final_context_cache, dict) and final_context_cache.get("hit") is True:
        return True
    return bool(
        isinstance(first_context_cache, dict)
        and first_context_cache.get("hit") is True
    )


def _visual_refresh_reason(
    first_context_cache: dict[str, Any] | None,
    final_context_cache: dict[str, Any] | None,
) -> str | None:
    for context_cache in (first_context_cache, final_context_cache):
        if not isinstance(context_cache, dict):
            continue
        reason = context_cache.get("refresh_reason")
        if isinstance(reason, str) and reason:
            return reason
    return None
