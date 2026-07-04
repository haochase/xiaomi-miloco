# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Voice-facing scene trigger aliases for XiaoAi/MiHome integrations."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from miloco.life.device_state_watcher import (
    build_device_state_watcher_status,
    read_device_state_watcher_config,
)
from miloco.life.router import LifeSceneTriggerRequest, LifeVoiceCommandRequest
from miloco.life.scene_trigger import LifeSceneIntent, LifeSceneTriggerPayload
from miloco.life.scene_trigger import (
    run_life_scene_trigger as run_life_scene_trigger_service,
)
from miloco.life.voice_session import (
    DEFAULT_CAMERA_CHANNEL,
    DEFAULT_CAMERA_DURATION_MS,
)
from miloco.life.voice_session import (
    run_life_voice_command as run_life_voice_command_service,
)
from miloco.schema.common_schema import NormalResponse

router = APIRouter(prefix="/voice", tags=["Voice"])
logger = logging.getLogger(__name__)
_SCENE_TASKS: set[asyncio.Task[object]] = set()
_SCENE_RUNS: dict[str, dict[str, object]] = {}
_MAX_SCENE_RUNS = 100
_SCENE_RUN_SEQUENCE = 0
_DEVICE_STATE_WATCHER_LOOP_SERVICE: object | None = None
_VISUAL_SCENE_INTENTS: set[LifeSceneIntent] = {"outfit_check", "cooking_check"}
_TRUTHY_ENV = {"1", "true", "yes", "on"}
_SCENE_ALIAS_BY_SLUG: dict[str, LifeSceneIntent] = {
    "outfit-check": "outfit_check",
    "outfit-suggest": "outfit_suggest",
    "cooking-check": "cooking_check",
    "cooking-suggest": "cooking_suggest",
}


def clear_life_scene_trigger_runs() -> None:
    global _SCENE_RUN_SEQUENCE
    _SCENE_RUNS.clear()
    _SCENE_RUN_SEQUENCE = 0


def get_life_scene_trigger_run_service(run_id: str) -> dict[str, object] | None:
    return _SCENE_RUNS.get(run_id)


def get_latest_life_scene_trigger_run_service() -> dict[str, object] | None:
    if not _SCENE_RUNS:
        return None
    latest_id = max(
        _SCENE_RUNS,
        key=lambda key: (
            int(_SCENE_RUNS[key].get("created_at_ms", 0)),
            int(_SCENE_RUNS[key].get("sequence", 0)),
        ),
    )
    return _SCENE_RUNS[latest_id]


def set_device_state_watcher_loop_service(loop: object | None) -> None:
    global _DEVICE_STATE_WATCHER_LOOP_SERVICE
    _DEVICE_STATE_WATCHER_LOOP_SERVICE = loop


def get_device_state_watcher_loop_service() -> object | None:
    return _DEVICE_STATE_WATCHER_LOOP_SERVICE


def enqueue_life_scene_trigger_service(
    payload: LifeSceneTriggerPayload,
) -> dict[str, object]:
    global _SCENE_RUN_SEQUENCE
    run_id = f"life_scene_async_{uuid4().hex}"
    _SCENE_RUN_SEQUENCE += 1
    _remember_scene_run(
        run_id,
        {
            "run_id": run_id,
            "intent": payload.intent,
            "action": "accepted",
            "async_mode": True,
            "status": "accepted",
            "status_endpoint": f"/api/voice/scene-runs/{run_id}",
            "created_at_ms": _now_ms(),
            "updated_at_ms": _now_ms(),
            "sequence": _SCENE_RUN_SEQUENCE,
            "result": None,
            "error": None,
        },
    )
    task = asyncio.create_task(_run_scene_trigger_background(run_id, payload))
    _SCENE_TASKS.add(task)
    task.add_done_callback(_SCENE_TASKS.discard)
    return {
        "run_id": run_id,
        "intent": payload.intent,
        "action": "accepted",
        "async_mode": True,
        "status": "accepted",
        "status_endpoint": f"/api/voice/scene-runs/{run_id}",
    }


async def _run_scene_trigger_background(
    run_id: str,
    payload: LifeSceneTriggerPayload,
) -> None:
    _update_scene_run(run_id, status="running", updated_at_ms=_now_ms())
    try:
        result = await run_life_scene_trigger_service(payload)
        _update_scene_run(
            run_id,
            status="completed",
            action=result.get("action"),
            updated_at_ms=_now_ms(),
            result=result,
            error=None,
        )
        logger.info(
            "voice scene trigger background completed: run_id=%s intent=%s action=%s",
            run_id,
            payload.intent,
            result.get("action"),
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "voice scene trigger background failed: run_id=%s intent=%s",
            run_id,
            payload.intent,
        )
        _update_scene_run(
            run_id,
            status="failed",
            updated_at_ms=_now_ms(),
            error="scene trigger background failed; check server logs",
        )


def _remember_scene_run(run_id: str, data: dict[str, object]) -> None:
    _SCENE_RUNS[run_id] = data
    while len(_SCENE_RUNS) > _MAX_SCENE_RUNS:
        oldest = min(
            _SCENE_RUNS,
            key=lambda key: int(_SCENE_RUNS[key].get("created_at_ms", 0)),
        )
        _SCENE_RUNS.pop(oldest, None)


def _update_scene_run(run_id: str, **updates: object) -> None:
    current = _SCENE_RUNS.get(run_id)
    if current is None:
        return
    current.update(updates)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _default_speaker_id() -> str | None:
    return os.getenv("MILOCO_LIFE_XIAOMI_SPEAKER_ID") or None


def _default_camera_id() -> str | None:
    return os.getenv("MILOCO_LIFE_CAMERA_ID") or None


def _trigger_gateway_config() -> dict[str, object]:
    audit_passed = _env_bool("MILOCO_LIFE_IDLE_RESOURCE_AUDIT_PASSED", False)
    enabled = _env_bool("MILOCO_LIFE_TRIGGER_GATEWAY_ENABLED", False)
    return {
        "enabled": enabled,
        "mode": os.getenv("MILOCO_LIFE_TRIGGER_GATEWAY_MODE") or "manual_scene_event",
        "idle_poll_interval_ms": _env_int(
            "MILOCO_LIFE_IDLE_POLL_INTERVAL_MS",
            default=30000,
            minimum=30000,
        ),
        "active_poll_interval_ms": _env_int(
            "MILOCO_LIFE_ACTIVE_POLL_INTERVAL_MS",
            default=2000,
            minimum=1000,
        ),
        "ttl_seconds": _env_int(
            "MILOCO_LIFE_TRIGGER_TTL_SECONDS",
            default=90,
            minimum=60,
        ),
        "max_empty_backoff_ms": _env_int(
            "MILOCO_LIFE_MAX_EMPTY_BACKOFF_MS",
            default=120000,
            minimum=60000,
        ),
        "autostart_allowed": bool(enabled and audit_passed),
        "idle_resource_audit_required": True,
        "idle_resource_audit_passed": audit_passed,
        "polls_trigger_metadata_only": True,
        "forbidden_during_detection": [
            "camera",
            "speaker",
            "mimo",
            "life_agent",
        ],
    }


def _scene_default_items() -> list[dict[str, object]]:
    return [
        _scene_default_item(
            slug="outfit-suggest",
            intent="outfit_suggest",
            requires_visual=False,
        ),
        _scene_default_item(
            slug="outfit-check",
            intent="outfit_check",
            requires_visual=True,
        ),
        _scene_default_item(
            slug="cooking-suggest",
            intent="cooking_suggest",
            requires_visual=False,
        ),
        _scene_default_item(
            slug="cooking-check",
            intent="cooking_check",
            requires_visual=True,
        ),
    ]


def _scene_default_item(
    *,
    slug: str,
    intent: LifeSceneIntent,
    requires_visual: bool,
) -> dict[str, object]:
    return {
        "slug": slug,
        "intent": intent,
        "path": f"/api/voice/scene/{slug}",
        "silent_path": f"/api/voice/scene-silent/{slug}",
        "requires_visual": requires_visual,
        "uses_speaker": True,
        "async_mode": True,
    }


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUTHY_ENV


def _env_int(
    name: str,
    *,
    default: int,
    minimum: int,
) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(minimum, parsed)


def _device_state_watcher_status() -> dict[str, object]:
    loop = get_device_state_watcher_loop_service()
    if loop is not None and hasattr(loop, "status"):
        status = loop.status()
        if isinstance(status, dict):
            return status
    return build_device_state_watcher_status(
        config=read_device_state_watcher_config(),
        running=False,
    )


async def _handle_voice_scene_request(
    request: LifeSceneTriggerRequest,
) -> NormalResponse:
    if request.async_mode:
        return NormalResponse(
            code=0,
            message="accepted",
            data=enqueue_life_scene_trigger_service(request.to_scene_payload()),
        )
    return NormalResponse(
        code=0,
        message="ok",
        data=await run_life_scene_trigger_service(request.to_scene_payload()),
    )


def _build_scene_alias_request(
    *,
    intent: LifeSceneIntent,
    speaker_id: str | None,
    camera_id: str | None,
    camera_channel: int,
    camera_duration_ms: int,
    suppress_speaker: bool,
    async_mode: bool,
) -> LifeSceneTriggerRequest:
    requires_visual = intent in _VISUAL_SCENE_INTENTS
    return LifeSceneTriggerRequest(
        intent=intent,
        speaker_id=speaker_id or _default_speaker_id(),
        camera_id=(camera_id or _default_camera_id()) if requires_visual else None,
        camera_channel=camera_channel,
        camera_duration_ms=camera_duration_ms,
        suppress_speaker=suppress_speaker,
        async_mode=async_mode,
    )


@router.get(
    "/scene-defaults",
    summary="Read queryless voice scene default device configuration",
    response_model=NormalResponse,
)
async def get_voice_scene_defaults() -> NormalResponse:
    return NormalResponse(
        code=0,
        message="ok",
        data={
            "speaker_id": _default_speaker_id(),
            "camera_id": _default_camera_id(),
            "default_speaker_outfit_suggest": "/api/voice/scene/outfit-suggest",
            "default_camera_speaker_outfit_check": "/api/voice/scene/outfit-check",
            "default_speaker_cooking_suggest": "/api/voice/scene/cooking-suggest",
            "default_camera_speaker_cooking_check": "/api/voice/scene/cooking-check",
            "default_silent_outfit_suggest": "/api/voice/scene-silent/outfit-suggest",
            "default_silent_cooking_suggest": "/api/voice/scene-silent/cooking-suggest",
            "scenes": _scene_default_items(),
            "trigger_gateway": _trigger_gateway_config(),
            "device_state_watcher": _device_state_watcher_status(),
        },
    )


@router.get(
    "/scene-runs/latest",
    summary="Read the latest asynchronous voice scene trigger run status",
    response_model=NormalResponse,
)
async def get_latest_voice_scene_run() -> NormalResponse:
    run = get_latest_life_scene_trigger_run_service()
    if run is None:
        raise HTTPException(status_code=404, detail="scene run not found")
    return NormalResponse(code=0, message="ok", data=run)


@router.get(
    "/scene-runs/{run_id}",
    summary="Read one asynchronous voice scene trigger run status",
    response_model=NormalResponse,
)
async def get_voice_scene_run(run_id: str) -> NormalResponse:
    run = get_life_scene_trigger_run_service(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="scene run not found")
    return NormalResponse(code=0, message="ok", data=run)


@router.post(
    "/scene-trigger",
    summary="Handle one XiaoAi/MiHome voice scene trigger for life agents",
    response_model=NormalResponse,
)
async def post_voice_scene_trigger(
    payload: LifeSceneTriggerRequest,
) -> NormalResponse:
    return await _handle_voice_scene_request(payload)


@router.post(
    "/command",
    summary="Handle one ASR text voice command for life agents",
    response_model=NormalResponse,
)
async def post_voice_command(payload: LifeVoiceCommandRequest) -> NormalResponse:
    return NormalResponse(
        code=0,
        message="ok",
        data=await run_life_voice_command_service(payload),
    )


@router.get(
    "/scene-trigger",
    summary="Handle one URL-friendly XiaoAi/MiHome voice scene trigger",
    response_model=NormalResponse,
)
async def get_voice_scene_trigger(
    intent: LifeSceneIntent,
    text: str | None = None,
    session_id: str | None = None,
    speaker_id: str | None = None,
    camera_id: str | None = None,
    camera_channel: int = DEFAULT_CAMERA_CHANNEL,
    camera_duration_ms: int = DEFAULT_CAMERA_DURATION_MS,
    trigger_source: str = "voice_intent",
    source_id: str | None = None,
    occasion: str | None = None,
    weather: str | None = None,
    people_count: int | None = None,
    time_budget_minutes: int | None = None,
    persist: bool = True,
    db_path: str | None = None,
    ack_message: str | None = None,
    suppress_speaker: bool = Query(default=False),
    async_mode: bool = Query(default=True),
) -> NormalResponse:
    request = LifeSceneTriggerRequest(
        intent=intent,
        text=text,
        session_id=session_id,
        speaker_id=speaker_id,
        camera_id=camera_id,
        camera_channel=camera_channel,
        camera_duration_ms=camera_duration_ms,
        trigger_source=trigger_source,
        source_id=source_id,
        occasion=occasion,
        weather=weather,
        people_count=people_count,
        time_budget_minutes=time_budget_minutes,
        persist=persist,
        db_path=db_path,
        ack_message=ack_message,
        suppress_speaker=suppress_speaker,
        async_mode=async_mode,
    )
    return await _handle_voice_scene_request(request)


@router.get(
    "/scene/{scene_slug}",
    summary="Handle one short URL XiaoAi/MiHome scene trigger alias",
    response_model=NormalResponse,
)
async def get_voice_scene_alias(
    scene_slug: str,
    speaker_id: str | None = None,
    camera_id: str | None = None,
    camera_channel: int = DEFAULT_CAMERA_CHANNEL,
    camera_duration_ms: int = DEFAULT_CAMERA_DURATION_MS,
    suppress_speaker: bool = Query(default=False),
    async_mode: bool = Query(default=True),
) -> NormalResponse:
    intent = _SCENE_ALIAS_BY_SLUG.get(scene_slug)
    if intent is None:
        raise HTTPException(status_code=404, detail="voice scene alias not found")
    return await _handle_voice_scene_request(
        _build_scene_alias_request(
            intent=intent,
            speaker_id=speaker_id,
            camera_id=camera_id,
            camera_channel=camera_channel,
            camera_duration_ms=camera_duration_ms,
            suppress_speaker=suppress_speaker,
            async_mode=async_mode,
        )
    )


@router.get(
    "/scene-silent/{scene_slug}",
    summary="Handle one path-only silent XiaoAi/MiHome scene trigger alias",
    response_model=NormalResponse,
)
async def get_voice_scene_silent_alias(scene_slug: str) -> NormalResponse:
    intent = _SCENE_ALIAS_BY_SLUG.get(scene_slug)
    if intent is None:
        raise HTTPException(status_code=404, detail="voice scene alias not found")
    return await _handle_voice_scene_request(
        _build_scene_alias_request(
            intent=intent,
            speaker_id=None,
            camera_id=None,
            camera_channel=DEFAULT_CAMERA_CHANNEL,
            camera_duration_ms=DEFAULT_CAMERA_DURATION_MS,
            suppress_speaker=True,
            async_mode=True,
        )
    )
