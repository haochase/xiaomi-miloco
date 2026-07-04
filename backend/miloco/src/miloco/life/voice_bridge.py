# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Bridge detected speech turns to on-demand life-agent voice sessions."""

from __future__ import annotations

import base64
import logging
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from miloco.life.intent import (
    COOKING_INITIAL_TERMS,
    infer_life_occasion,
    is_life_voice_candidate,
    matched_life_terms,
)
from miloco.life.service import LifeTriggerSource
from miloco.life.voice_session import (
    DEFAULT_CAMERA_CHANNEL,
    DEFAULT_CAMERA_DURATION_MS,
    run_life_voice_command,
)
from miloco.miot.schema import DeviceControlRequest

if TYPE_CHECKING:
    from miloco.perception.types import Speech

logger = logging.getLogger(__name__)

_SPEAKER_CACHE: dict[str, tuple[str, str]] = {}


@dataclass(frozen=True)
class _BridgeVoicePayload:
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
    people_count: int = 2
    time_budget_minutes: int = 20
    persist: bool = True
    db_path: str | None = None


async def run_life_voice_turn_from_speech(speech: Speech) -> bool:
    """Consume one speech if it belongs to the life-agent voice path."""
    if not speech.needs_response or not speech.is_complete:
        return False
    if not is_life_voice_candidate(speech.content):
        return False

    payload = _payload_from_speech(speech)
    first = await run_life_voice_command(payload)
    if not first.get("matched"):
        return False

    response = first
    if first.get("needs_visual_capture"):
        camera_request = first.get("camera_request") or {}
        camera_id = str(camera_request.get("camera_id") or payload.camera_id or "")
        if not camera_id:
            logger.warning("life voice bridge needs visual capture but has no camera id")
            return True
        try:
            clip_bytes = await record_life_camera_clip(
                camera_id=camera_id,
                channel=int(camera_request.get("channel", payload.camera_channel)),
                duration_ms=int(
                    camera_request.get("duration_ms", payload.camera_duration_ms)
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("life voice bridge camera clip failed: %s", exc)
            return True

        response = await run_life_voice_command(
            _payload_from_speech(
                speech,
                session_id=str(first.get("session_id") or ""),
                camera_id=camera_id,
                camera_channel=int(camera_request.get("channel", payload.camera_channel)),
                camera_duration_ms=int(
                    camera_request.get("duration_ms", payload.camera_duration_ms)
                ),
                source_id=f"voice_camera_{camera_id}_{int(time.time())}",
                prompt=_prompt_for_text(speech.content),
                clip_base64=base64.b64encode(clip_bytes).decode("ascii"),
            )
        )

    speaker_request = response.get("speaker_request")
    if isinstance(speaker_request, dict):
        await play_xiaomi_speaker_request(speaker_request)
    return True


def _payload_from_speech(
    speech: Speech,
    *,
    session_id: str | None = None,
    camera_id: str | None = None,
    camera_channel: int | None = None,
    camera_duration_ms: int | None = None,
    source_id: str | None = None,
    prompt: str | None = None,
    clip_base64: str | None = None,
) -> _BridgeVoicePayload:
    return _BridgeVoicePayload(
        text=speech.content,
        session_id=session_id,
        speaker_id=os.getenv("MILOCO_LIFE_XIAOMI_SPEAKER_ID") or None,
        camera_id=camera_id or _camera_id_from_speech(speech),
        camera_channel=camera_channel
        or _int_env("MILOCO_LIFE_CAMERA_CHANNEL", DEFAULT_CAMERA_CHANNEL),
        camera_duration_ms=camera_duration_ms
        or _int_env("MILOCO_LIFE_CAMERA_DURATION_MS", DEFAULT_CAMERA_DURATION_MS),
        source_id=source_id,
        prompt=prompt,
        clip_base64=clip_base64,
        occasion=infer_life_occasion(
            speech.content,
            default=os.getenv("MILOCO_LIFE_OCCASION") or None,
        ),
        weather=os.getenv("MILOCO_LIFE_WEATHER") or None,
        people_count=_int_env("MILOCO_LIFE_PEOPLE_COUNT", 2),
        time_budget_minutes=_int_env("MILOCO_LIFE_TIME_BUDGET_MINUTES", 20),
        persist=_bool_env("MILOCO_LIFE_PERSIST", True),
        db_path=os.getenv("MILOCO_LIFE_DB_PATH") or "data/life-demo.db",
    )


def _camera_id_from_speech(speech: Speech) -> str | None:
    if speech.source_device_ids:
        return speech.source_device_ids[0]
    return os.getenv("MILOCO_LIFE_CAMERA_ID") or None


def _prompt_for_text(text: str) -> str:
    if matched_life_terms(text, COOKING_INITIAL_TERMS):
        return (
            "Focus on visible ingredients, fridge items, kitchen tools, cooking "
            "state, uncertainty, and conservative safety-aware cooking advice."
        )
    return (
        "Focus on visible clothing, shoes, accessories, worn outfit, uncertain "
        "items, and conservative outfit advice."
    )


async def record_life_camera_clip(
    *,
    camera_id: str,
    channel: int,
    duration_ms: int,
) -> bytes:
    from miloco.miot.ws import NalClipRecorder, miot_video_stream_manager

    recorder = NalClipRecorder(duration_ms=duration_ms)
    registered = False
    try:
        await miot_video_stream_manager.register_recorder(camera_id, channel, recorder)
        registered = True
        return await recorder.wait(timeout=duration_ms / 1000.0 + 8.0)
    finally:
        recorder.cancel()
        if registered:
            await miot_video_stream_manager.unregister_recorder(
                camera_id, channel, recorder
            )


async def play_xiaomi_speaker_request(request: dict[str, Any]) -> dict[str, Any]:
    message = str(request.get("message") or "").strip()
    if not message:
        return {"delivered": False, "reason": "empty message"}
    preferred = request.get("preferred_device_id")
    return await play_xiaomi_speaker_message(
        message,
        str(preferred) if preferred else None,
    )


async def play_xiaomi_speaker_message(
    message: str,
    preferred_device_id: str | None = None,
) -> dict[str, Any]:
    message = message.strip()
    if not message:
        return {"delivered": False, "reason": "empty message"}

    from miloco.manager import get_manager

    miot_service = get_manager().miot_service
    speaker = await _resolve_xiaomi_speaker(
        miot_service,
        preferred_device_id,
    )
    if speaker is None:
        logger.warning("life voice bridge found no Xiaomi speaker play-text action")
        return {"delivered": False, "reason": "no speaker play-text action"}

    did, action_iid = speaker
    control = await miot_service.control_device(
        did,
        DeviceControlRequest(
            type="call_action",
            iid=action_iid,
            params=[message],
        ),
    )
    logger.info("life voice bridge speaker playback delivered to %s.%s", did, action_iid)
    return {
        "delivered": True,
        "did": did,
        "action": action_iid,
        "control_result": control,
    }


async def _resolve_xiaomi_speaker(
    miot_service,
    preferred_device_id: str | None,
) -> tuple[str, str] | None:
    cache_key = preferred_device_id or "__auto__"
    if cache_key in _SPEAKER_CACHE:
        return _SPEAKER_CACHE[cache_key]

    if preferred_device_id:
        action_iid = await _play_text_action_for_device(miot_service, preferred_device_id)
        if action_iid:
            _SPEAKER_CACHE[cache_key] = (preferred_device_id, action_iid)
            return _SPEAKER_CACHE[cache_key]

    for device in await miot_service.get_miot_device_list():
        did = str(_field(device, "did", ""))
        name = str(_field(device, "name", ""))
        model = str(_field(device, "model", ""))
        if not did or not _looks_like_speaker(name, model):
            continue
        action_iid = await _play_text_action_for_device(miot_service, did)
        if action_iid:
            _SPEAKER_CACHE[cache_key] = (did, action_iid)
            return _SPEAKER_CACHE[cache_key]
    return None


async def _play_text_action_for_device(miot_service, did: str) -> str | None:
    try:
        spec_data = await miot_service.get_device_spec(did)
    except Exception as exc:  # noqa: BLE001
        logger.warning("life voice bridge failed to read speaker spec %s: %s", did, exc)
        return None
    return _find_play_text_action(spec_data)


def _find_play_text_action(spec_data: Any) -> str | None:
    if isinstance(spec_data, dict) and isinstance(spec_data.get("data"), dict):
        spec_data = spec_data["data"]
    spec_map = spec_data.get("spec") if isinstance(spec_data, dict) else None
    if not isinstance(spec_map, dict):
        spec_map = spec_data if isinstance(spec_data, dict) else {}
    for iid, entry in spec_map.items():
        if not isinstance(entry, dict):
            continue
        text = " ".join(
            str(entry.get(key, ""))
            for key in ("type", "type_name", "description", "name")
        ).lower()
        if "play-text" in text or "\u64ad\u653e\u6587\u672c" in text:
            return str(iid)
    return "action.5.3" if "action.5.3" in spec_map else None


def _looks_like_speaker(name: str, model: str) -> bool:
    text = f"{name} {model}".lower()
    return (
        "speaker" in text
        or "wifispeaker" in text
        or "\u97f3\u7bb1" in name
        or "\u5c0f\u7231" in name
    )


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}
