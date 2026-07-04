# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Short-lived camera microphone listener for life-agent voice turns."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import time
import wave
from dataclasses import dataclass
from typing import Any

import numpy as np

from miloco.life.resource_lease import ResourceLeaseManager
from miloco.life.voice_bridge import (
    play_xiaomi_speaker_request,
    record_life_camera_clip,
)
from miloco.life.voice_session import (
    DEFAULT_CAMERA_CHANNEL,
    DEFAULT_CAMERA_DURATION_MS,
    run_life_voice_command,
)
from miloco.perception.engine.omni.omni_client import OmniError

logger = logging.getLogger(__name__)

_CAMERA_VOICE_LEASE_MANAGER = ResourceLeaseManager()
_ASR_SYSTEM_PROMPT = (
    "You are a precise ASR adapter for a smart-home assistant. Return only JSON "
    'with this shape: {"transcript":"..."} . Transcribe the user speech in '
    "simplified Chinese when Chinese is spoken. Do not answer the command."
)
_DEFAULT_ASR_PROMPT = (
    "Transcribe the user's Chinese speech command from the camera microphone."
)


@dataclass(frozen=True)
class CameraVoiceWindow:
    """A short camera microphone capture window."""

    camera_id: str
    channel: int
    requested_duration_ms: int
    audio_base64: str | None = None
    clip_base64: str | None = None
    audio_bytes: int = 0
    clip_bytes: int = 0
    error: str | None = None


@dataclass(frozen=True)
class CameraVoiceListenPayload:
    """Input for one short-lived camera voice listener run."""

    camera_id: str
    speaker_id: str | None = None
    camera_channel: int = DEFAULT_CAMERA_CHANNEL
    listen_duration_ms: int = 3000
    camera_duration_ms: int = DEFAULT_CAMERA_DURATION_MS
    transcript: str | None = None
    session_id: str | None = None
    source_id: str | None = None
    prompt: str | None = None
    clip_base64: str | None = None
    mimo_payload: dict[str, Any] | str | None = None
    occasion: str = "\u4eca\u5929\u51fa\u95e8"
    weather: str | None = None
    people_count: int = 1
    time_budget_minutes: int = 30
    persist: bool = True
    db_path: str | None = None
    speak: bool = True
    life_mimo_base_url: str | None = None
    life_mimo_vision_model: str | None = None
    life_mimo_asr_model: str | None = None
    fresh_session: bool = False
    force_visual_capture: bool = False


@dataclass(frozen=True)
class _VoicePayload:
    text: str
    session_id: str | None = None
    speaker_id: str | None = None
    camera_id: str | None = None
    camera_channel: int = DEFAULT_CAMERA_CHANNEL
    camera_duration_ms: int = DEFAULT_CAMERA_DURATION_MS
    trigger_source: str = "voice_intent"
    source_id: str | None = None
    prompt: str | None = None
    clip_base64: str | None = None
    mimo_payload: dict[str, Any] | str | None = None
    occasion: str = "\u4eca\u5929\u51fa\u95e8"
    weather: str | None = None
    people_count: int = 1
    time_budget_minutes: int = 30
    persist: bool = True
    db_path: str | None = None
    fresh_session: bool = False
    force_visual_capture: bool = False


async def run_camera_voice_listen(
    payload: CameraVoiceListenPayload,
) -> dict[str, Any]:
    """Run one short camera-microphone listen -> life-agent -> speaker turn."""
    started_at = time.perf_counter()
    transcript = (payload.transcript or "").strip()
    capture: CameraVoiceWindow | None = None
    source = "provided_transcript" if transcript else "camera_audio"

    if not transcript:
        with _life_mimo_request_overrides(payload):
            capture = await capture_camera_voice_window(
                camera_id=payload.camera_id,
                channel=payload.camera_channel,
                duration_ms=payload.listen_duration_ms,
                include_audio=True,
                include_clip=False,
            )
            if capture.audio_base64:
                try:
                    transcript = (
                        await transcribe_camera_voice_audio(
                            capture.audio_base64,
                            prompt=_DEFAULT_ASR_PROMPT,
                        )
                    ).strip()
                except OmniError as exc:
                    return _asr_failed_result(
                        payload,
                        source=source,
                        capture=capture,
                        started_at=started_at,
                        error=str(exc),
                        diagnostics=_life_mimo_diagnostics(task="asr"),
                    )

    if not transcript:
        return _empty_result(
            payload,
            source=source,
            capture=capture,
            started_at=started_at,
            reason="no_transcript",
        )

    try:
        first = await run_life_voice_command(
            _voice_payload(payload, text=transcript, visual=False)
        )
    except OmniError as exc:
        return _life_voice_failed_result(
            payload,
            source=source,
            transcript=transcript,
            capture=capture,
            started_at=started_at,
            error=str(exc),
        )
    final = first
    if first.get("needs_visual_capture"):
        if (
            payload.clip_base64 is None
            and payload.mimo_payload is None
            and (capture is None or capture.clip_base64 is None)
        ):
            visual_capture = await capture_camera_voice_window(
                camera_id=payload.camera_id,
                channel=payload.camera_channel,
                duration_ms=payload.camera_duration_ms,
                include_audio=False,
                include_clip=True,
            )
            capture = _merge_capture_windows(capture, visual_capture)
        with _life_mimo_request_overrides(payload):
            try:
                final = await run_life_voice_command(
                    _voice_payload(
                        payload,
                        text=transcript,
                        session_id=str(
                            first.get("session_id") or payload.session_id or ""
                        ),
                        source_id=(
                            payload.source_id
                            or _capture_source_id(payload.camera_id, source=source)
                        ),
                        clip_base64=payload.clip_base64
                        or (capture.clip_base64 if capture else None),
                        mimo_payload=payload.mimo_payload,
                        visual=True,
                    )
                )
            except OmniError as exc:
                final = _mimo_failed_response(
                    first,
                    error=str(exc),
                    diagnostics=_life_mimo_diagnostics(task="vision"),
                )

    playback = None
    speaker_request = final.get("speaker_request")
    if payload.speak and isinstance(speaker_request, dict):
        playback = await _play_speaker_with_diagnostics(speaker_request)

    return _result_payload(
        matched=bool(final.get("matched")),
        source=source,
        transcript=transcript,
        domain=final.get("domain") or first.get("domain"),
        capture=_capture_payload(capture, skipped=capture is None),
        first=first,
        final=final,
        playback=playback,
        timing=_timing(started_at),
    )


async def capture_camera_voice_window(
    *,
    camera_id: str,
    channel: int,
    duration_ms: int,
    include_audio: bool = True,
    include_clip: bool = True,
) -> CameraVoiceWindow:
    """Capture one short camera audio window plus a video-only visual clip."""
    duration_ms = max(1000, min(duration_ms, 10000))
    lease = await _CAMERA_VOICE_LEASE_MANAGER.try_acquire("camera_voice", camera_id)
    if not lease.acquired:
        return CameraVoiceWindow(
            camera_id=camera_id,
            channel=channel,
            requested_duration_ms=duration_ms,
            error="camera_voice_lease_busy",
        )

    audio_result: tuple[str | None, int] = (None, 0)
    clip_result: tuple[str | None, int] = (None, 0)
    try:
        audio_task = (
            asyncio.create_task(
                _record_camera_audio_base64(
                    camera_id=camera_id,
                    channel=channel,
                    duration_ms=duration_ms,
                )
            )
            if include_audio
            else None
        )
        clip_task = (
            asyncio.create_task(
                _record_camera_clip_base64(
                    camera_id=camera_id,
                    channel=channel,
                    duration_ms=duration_ms,
                )
            )
            if include_clip
            else None
        )
        tasks = [task for task in (audio_task, clip_task) if task is not None]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        result_index = 0
        if include_audio:
            audio_result = _capture_tuple(results[result_index])
            result_index += 1
        if include_clip:
            clip_result = _capture_tuple(results[result_index])
        error = _capture_error(results)
        return CameraVoiceWindow(
            camera_id=camera_id,
            channel=channel,
            requested_duration_ms=duration_ms,
            audio_base64=audio_result[0],
            audio_bytes=audio_result[1],
            clip_base64=clip_result[0],
            clip_bytes=clip_result[1],
            error=error,
        )
    finally:
        await lease.release(reason="completed")


async def transcribe_camera_voice_audio(
    audio_base64: str,
    *,
    prompt: str = _DEFAULT_ASR_PROMPT,
) -> str:
    """Transcribe one camera microphone audio clip with the configured MiMo model."""
    from miloco.life.mimo_client import call_life_mimo_chat
    from miloco.perception.engine.omni.response_parser import extract_json

    raw = await call_life_mimo_chat(
        system_prompt=_ASR_SYSTEM_PROMPT,
        user_content=prompt,
        audio_base64=audio_base64,
        task="asr",
        max_completion_tokens=180,
        temperature=0.0,
        timeout=30.0,
    )
    content = str(raw.get("choices", [{}])[0].get("message", {}).get("content") or "")
    if not content.strip():
        return ""
    try:
        data = json.loads(extract_json(content))
    except (json.JSONDecodeError, ValueError, TypeError):
        return content.strip()
    transcript = data.get("transcript") if isinstance(data, dict) else None
    return str(transcript or "").strip()


def _voice_payload(
    payload: CameraVoiceListenPayload,
    *,
    text: str,
    visual: bool,
    session_id: str | None = None,
    source_id: str | None = None,
    clip_base64: str | None = None,
    mimo_payload: dict[str, Any] | str | None = None,
) -> _VoicePayload:
    return _VoicePayload(
        text=text,
        session_id=session_id or payload.session_id,
        speaker_id=payload.speaker_id,
        camera_id=payload.camera_id,
        camera_channel=payload.camera_channel,
        camera_duration_ms=payload.camera_duration_ms,
        source_id=source_id or payload.source_id,
        prompt=payload.prompt
        or (
            "Use the camera microphone transcript as the user intent and the "
            "short camera window as visual context. Reply in simplified Chinese."
        ),
        clip_base64=clip_base64 if visual else None,
        mimo_payload=mimo_payload if visual else None,
        occasion=payload.occasion,
        weather=payload.weather,
        people_count=payload.people_count,
        time_budget_minutes=payload.time_budget_minutes,
        persist=payload.persist,
        db_path=payload.db_path,
        fresh_session=payload.fresh_session if session_id is None else False,
        force_visual_capture=payload.force_visual_capture if not visual else False,
    )


async def _record_camera_clip_base64(
    *,
    camera_id: str,
    channel: int,
    duration_ms: int,
) -> tuple[str | None, int]:
    clip = await record_life_camera_clip(
        camera_id=camera_id,
        channel=channel,
        duration_ms=duration_ms,
    )
    if not clip:
        return None, 0
    return base64.b64encode(clip).decode("ascii"), len(clip)


async def _record_camera_audio_base64(
    *,
    camera_id: str,
    channel: int,
    duration_ms: int,
) -> tuple[str | None, int]:
    from miloco.manager import get_manager

    chunks: list[np.ndarray] = []

    async def on_audio(
        _did: str,
        frame,
        _ts: int,
        _channel: int,
        _recv_unix_ms: int = 0,
        _decoded_unix_ms: int = 0,
    ) -> None:
        chunks.append(np.asarray(frame, dtype=np.int16).copy())

    miot_service = get_manager().miot_service
    reg_id = await miot_service.start_camera_decode_audio_stream(
        camera_id,
        channel,
        on_audio,
    )
    try:
        await asyncio.sleep(duration_ms / 1000.0)
    finally:
        if reg_id >= 0:
            await miot_service.stop_camera_decode_audio_stream(
                camera_id,
                channel,
                reg_id,
            )

    if not chunks:
        return None, 0
    audio = np.concatenate(chunks).astype(np.int16, copy=False)
    wav_bytes = _encode_pcm_wav_bytes(audio, sample_rate=16000)
    if not wav_bytes:
        return None, int(audio.nbytes)
    return base64.b64encode(wav_bytes).decode("ascii"), len(wav_bytes)


def _encode_pcm_wav_bytes(audio: np.ndarray, *, sample_rate: int) -> bytes:
    """Encode mono int16 PCM audio as WAV for MiMo ASR."""
    if audio is None or audio.size == 0:
        return b""
    pcm = np.asarray(audio, dtype="<i2").reshape(-1)
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm.tobytes())
        return buffer.getvalue()


def _capture_tuple(value: Any) -> tuple[str | None, int]:
    if isinstance(value, BaseException):
        return None, 0
    if not isinstance(value, tuple) or len(value) != 2:
        return None, 0
    encoded, size = value
    return (encoded if isinstance(encoded, str) and encoded else None, int(size or 0))


def _capture_error(values: list[Any]) -> str | None:
    errors = [str(value) for value in values if isinstance(value, BaseException)]
    return "; ".join(errors) if errors else None


def _merge_capture_windows(
    first: CameraVoiceWindow | None,
    second: CameraVoiceWindow,
) -> CameraVoiceWindow:
    if first is None:
        return second
    errors = [error for error in (first.error, second.error) if error]
    return CameraVoiceWindow(
        camera_id=second.camera_id or first.camera_id,
        channel=second.channel,
        requested_duration_ms=max(
            first.requested_duration_ms,
            second.requested_duration_ms,
        ),
        audio_base64=first.audio_base64 or second.audio_base64,
        clip_base64=second.clip_base64 or first.clip_base64,
        audio_bytes=first.audio_bytes or second.audio_bytes,
        clip_bytes=second.clip_bytes or first.clip_bytes,
        error="; ".join(errors) if errors else None,
    )


def _capture_payload(
    capture: CameraVoiceWindow | None,
    *,
    skipped: bool,
) -> dict[str, Any]:
    if capture is None:
        return {
            "skipped": skipped,
            "camera_id": None,
            "channel": None,
            "requested_duration_ms": None,
            "audio_bytes": 0,
            "clip_bytes": 0,
            "error": None,
        }
    return {
        "skipped": skipped,
        "camera_id": capture.camera_id,
        "channel": capture.channel,
        "requested_duration_ms": capture.requested_duration_ms,
        "audio_bytes": capture.audio_bytes,
        "clip_bytes": capture.clip_bytes,
        "error": capture.error,
    }


def _session_payload(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": response.get("session_id"),
        "session_active": bool(response.get("session_active", False)),
        "turn_count": int(response.get("turn_count") or 0),
        "used_last_context": bool(response.get("used_last_context", False)),
        "context_cache": response.get("context_cache"),
    }


def _result_payload(**values: Any) -> dict[str, Any]:
    final = values.get("final")
    if isinstance(final, dict) and "session" not in values:
        values["session"] = _session_payload(final)
    return values


def _empty_result(
    payload: CameraVoiceListenPayload,
    *,
    source: str,
    capture: CameraVoiceWindow | None,
    started_at: float,
    reason: str,
) -> dict[str, Any]:
    final = {
        "matched": False,
        "session_id": payload.session_id,
        "session_active": False,
        "domain": None,
        "action": "ignored",
        "needs_visual_capture": False,
        "camera_request": None,
        "trigger": None,
        "broadcast_text": None,
        "speaker_request": None,
        "reason": reason,
    }
    return _result_payload(
        matched=False,
        source=source,
        transcript="",
        domain=None,
        capture=_capture_payload(capture, skipped=capture is None),
        first=final,
        final=final,
        playback=None,
        timing=_timing(started_at),
    )


def _mimo_failed_response(
    first: dict[str, Any],
    *,
    error: str,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "matched": bool(first.get("matched")),
        "session_id": first.get("session_id"),
        "session_active": bool(first.get("session_active", True)),
        "domain": first.get("domain"),
        "action": "failed",
        "needs_visual_capture": False,
        "camera_request": None,
        "trigger": None,
        "broadcast_text": None,
        "speaker_request": None,
        "used_last_context": False,
        "context_cache": first.get("context_cache"),
        "turn_count": first.get("turn_count", 0),
        "reason": "mimo_error",
        "error": error,
        "diagnostics": diagnostics or {},
    }


def _asr_failed_result(
    payload: CameraVoiceListenPayload,
    *,
    source: str,
    capture: CameraVoiceWindow | None,
    started_at: float,
    error: str,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final = {
        "matched": False,
        "session_id": payload.session_id,
        "session_active": False,
        "domain": None,
        "action": "failed",
        "needs_visual_capture": False,
        "camera_request": None,
        "trigger": None,
        "broadcast_text": None,
        "speaker_request": None,
        "reason": "asr_error",
        "error": error,
        "diagnostics": diagnostics or {},
    }
    return _result_payload(
        matched=False,
        source=source,
        transcript="",
        domain=None,
        capture=_capture_payload(capture, skipped=capture is None),
        first=final,
        final=final,
        playback=None,
        timing=_timing(started_at),
    )


def _life_voice_failed_result(
    payload: CameraVoiceListenPayload,
    *,
    source: str,
    transcript: str,
    capture: CameraVoiceWindow | None,
    started_at: float,
    error: str,
) -> dict[str, Any]:
    final = {
        "matched": False,
        "session_id": payload.session_id,
        "session_active": False,
        "domain": None,
        "action": "failed",
        "needs_visual_capture": False,
        "camera_request": None,
        "trigger": None,
        "broadcast_text": None,
        "speaker_request": None,
        "used_last_context": False,
        "context_cache": None,
        "turn_count": 0,
        "reason": "life_voice_error",
        "error": error,
        "diagnostics": {"stage": "first_voice_turn"},
    }
    return _result_payload(
        matched=False,
        source=source,
        transcript=transcript,
        domain=None,
        capture=_capture_payload(capture, skipped=capture is None),
        first=final,
        final=final,
        playback=None,
        timing=_timing(started_at),
    )


async def _play_speaker_with_diagnostics(
    speaker_request: dict[str, Any],
) -> dict[str, Any]:
    try:
        return await play_xiaomi_speaker_request(speaker_request)
    except Exception as exc:  # noqa: BLE001
        preferred = speaker_request.get("preferred_device_id")
        logger.warning("camera voice speaker playback failed: %s", exc)
        return {
            "delivered": False,
            "did": str(preferred) if preferred else None,
            "action": None,
            "control_result": None,
            "error": str(exc),
            "reason": "speaker_playback_error",
        }


def _capture_source_id(camera_id: str, *, source: str) -> str:
    return f"{source}_{camera_id}_{int(time.time())}"


def _timing(started_at: float) -> dict[str, int]:
    return {
        "total_turn_latency_ms": max(0, int((time.perf_counter() - started_at) * 1000))
    }


def _life_mimo_request_overrides(payload: CameraVoiceListenPayload):
    from miloco.life.mimo_client import life_mimo_overrides

    return life_mimo_overrides(
        base_url=payload.life_mimo_base_url,
        vision_model=payload.life_mimo_vision_model,
        asr_model=payload.life_mimo_asr_model,
    )


def _life_mimo_diagnostics(*, task: str) -> dict[str, Any]:
    from miloco.config import get_settings
    from miloco.life.mimo_client import (
        resolve_life_mimo_base_url,
        resolve_life_mimo_model,
    )

    settings = get_settings()
    omni = settings.model.omni
    return {
        "life_mimo": {
            "base_url": resolve_life_mimo_base_url(configured_base_url=omni.base_url),
            "asr_model": resolve_life_mimo_model(
                configured_model=omni.model,
                task="asr",
            ),
            "vision_model": resolve_life_mimo_model(
                configured_model=omni.model,
                task="vision",
            ),
            "task": task,
        }
    }
