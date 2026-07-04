# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Short-lived voice session coordination for on-demand life agents."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import uuid4

from miloco.life.schema import LifeDomain
from miloco.life.service import (
    LifeTriggerSource,
    _classify_life_text_intent,
    run_life_text_trigger,
    run_life_trigger,
)

VoiceSessionAction = Literal[
    "ignored",
    "awaiting_visual_capture",
    "responded",
    "duplicate_ignored",
]

SESSION_TTL_MS = 120_000
DUPLICATE_SUPPRESS_MS = 8_000
DEFAULT_CAMERA_CHANNEL = 0
DEFAULT_CAMERA_DURATION_MS = 2_000
MIN_CAMERA_DURATION_MS = 2_000
MAX_CAMERA_DURATION_MS = 10_000

_FOLLOWUP_CAPTURE_TERMS = (
    "\u8fd9\u4ef6",
    "\u8fd9\u4e2a",
    "\u624b\u91cc",
    "\u62ff\u7740",
    "\u770b\u770b",
    "\u955c\u5934",
    "\u8eab\u4e0a",
    "\u7a7f\u7740",
    "\u6362\u4e86",
    "\u518d\u770b",
    "\u62cd",
    "this",
    "holding",
    "camera",
    "look at",
)
_CONTEXT_PREFIX = "\u6211\u5148\u6309\u521a\u624d\u770b\u5230\u7684\u7ed3\u679c\u7ee7\u7eed\u5efa\u8bae\uff1a"
_NO_CONTEXT_MESSAGE = (
    "\u6211\u8fd8\u6ca1\u6709\u53ef\u9760\u7684\u89c6\u89c9\u7ed3\u679c\uff0c"
    "\u9700\u8981\u5148\u770b\u4e00\u4e0b\u518d\u7ed9\u5efa\u8bae\u3002"
)


class LifeVoiceCommandPayload(Protocol):
    text: str
    session_id: str | None
    speaker_id: str | None
    camera_id: str | None
    camera_channel: int
    camera_duration_ms: int
    trigger_source: LifeTriggerSource
    source_id: str | None
    prompt: str | None
    clip_base64: str | None
    mimo_payload: dict[str, Any] | str | None
    occasion: str
    weather: str | None
    people_count: int
    time_budget_minutes: int
    persist: bool
    db_path: str | None
    fresh_session: bool
    force_visual_capture: bool


@dataclass
class _VoiceSession:
    session_id: str
    domain: LifeDomain
    speaker_id: str | None
    camera_id: str | None
    created_at_ms: int
    updated_at_ms: int
    expires_at_ms: int
    turn_count: int = 0
    last_text: str = ""
    last_text_at_ms: int = 0
    last_trigger: dict[str, Any] | None = None
    last_broadcast_text: str | None = None
    last_context_at_ms: int = 0
    last_context_source_id: str | None = None
    last_context_source_type: str | None = None
    occasion: str | None = None
    weather: str | None = None


@dataclass(frozen=True)
class _VoiceTriggerAdapter:
    trigger_source: LifeTriggerSource
    domain: LifeDomain
    source_id: str | None
    prompt: str | None
    clip_base64: str | None
    mimo_payload: dict[str, Any] | str | None
    occasion: str
    weather: str | None
    people_count: int
    time_budget_minutes: int
    persist: bool
    db_path: str | None


_SESSIONS: dict[str, _VoiceSession] = {}


def clear_life_voice_sessions() -> None:
    """Reset in-memory sessions for tests and local demos."""
    _SESSIONS.clear()


async def run_life_voice_command(payload: LifeVoiceCommandPayload) -> dict[str, Any]:
    """Run one speech turn without attaching life agents to realtime perception."""
    started_at = time.perf_counter()
    now_ms = _now_ms()
    _purge_expired(now_ms)
    text = payload.text.strip()
    has_visual_input = bool(payload.clip_base64 or payload.mimo_payload)
    fresh_session = bool(getattr(payload, "fresh_session", False))
    force_visual_capture = bool(getattr(payload, "force_visual_capture", False))
    text_intent = _classify_life_text_intent(text)
    session = _find_session(
        payload.session_id,
        now_ms,
        speaker_id=payload.speaker_id,
        camera_id=payload.camera_id,
        fresh_session=fresh_session,
    )
    if (
        session is not None
        and text_intent is not None
        and text_intent.domain != session.domain
    ):
        session = None

    if _is_duplicate_turn(session, text, now_ms, has_visual_input):
        return _with_latency(_duplicate_response(session), started_at)

    if session is None:
        text_trigger = await run_life_text_trigger(payload)
        if not text_trigger["matched"]:
            return _with_latency(_ignored_response(text_trigger), started_at)
        session = _create_session(
            domain=text_trigger["domain"],
            payload=payload,
            now_ms=now_ms,
        )
        session.occasion = _dict_str(text_trigger, "occasion") or payload.occasion
        session.weather = _dict_str(text_trigger, "weather") or payload.weather
        if text_trigger["needs_visual_capture"] or force_visual_capture:
            _remember_turn(session, text, now_ms)
            return _with_latency(
                _camera_response(
                    session,
                    payload,
                    reason=(
                        "forced_visual_capture"
                        if force_visual_capture
                        else "visible_object_reference"
                    ),
                    now_ms=now_ms,
                ),
                started_at,
            )
        return _with_latency(
            _responded_response(
                session,
                trigger_data=text_trigger["trigger"],
                payload=payload,
                text=text,
                now_ms=now_ms,
            ),
            started_at,
        )

    session.speaker_id = payload.speaker_id or session.speaker_id
    session.camera_id = payload.camera_id or session.camera_id
    if payload.occasion and payload.occasion.strip() not in {
        "today outing",
        "\u4eca\u5929\u51fa\u95e8",
        "\u4eca\u5929\u65e5\u5e38\u51fa\u95e8",
        "\u65e5\u5e38\u51fa\u95e8",
    }:
        session.occasion = payload.occasion
    if payload.weather and payload.weather.strip() not in {
        "\u8bf7\u6309\u4eca\u5929\u5f53\u5730\u5929\u6c14\u7ed9\u51fa\u4fdd\u5b88\u5efa\u8bae",
    }:
        session.weather = payload.weather
    if has_visual_input:
        trigger_data = await run_life_trigger(
            _VoiceTriggerAdapter(
                trigger_source=payload.trigger_source,
                domain=session.domain,
                source_id=payload.source_id,
                prompt=payload.prompt,
                clip_base64=payload.clip_base64,
                mimo_payload=payload.mimo_payload,
                occasion=session.occasion or payload.occasion,
                weather=session.weather or payload.weather,
                people_count=payload.people_count,
                time_budget_minutes=payload.time_budget_minutes,
                persist=payload.persist,
                db_path=payload.db_path,
            )
        )
        return _with_latency(
            _responded_response(
                session,
                trigger_data=trigger_data,
                payload=payload,
                text=text,
                now_ms=now_ms,
            ),
            started_at,
        )

    if _requires_followup_capture(text):
        _remember_turn(session, text, now_ms)
        return _with_latency(
            _camera_response(
                session,
                payload,
                reason="visible_object_reference",
                now_ms=now_ms,
            ),
            started_at,
        )

    return _with_latency(
        _context_response(session, payload, text=text, now_ms=now_ms),
        started_at,
    )


def _now_ms() -> int:
    return int(time.time() * 1000)


def _purge_expired(now_ms: int) -> None:
    expired_ids = [
        session_id
        for session_id, session in _SESSIONS.items()
        if session.expires_at_ms <= now_ms
    ]
    for session_id in expired_ids:
        _SESSIONS.pop(session_id, None)


def _find_session(
    session_id: str | None,
    now_ms: int,
    *,
    speaker_id: str | None = None,
    camera_id: str | None = None,
    fresh_session: bool = False,
) -> _VoiceSession | None:
    if session_id:
        session = _SESSIONS.get(session_id)
        if session is not None and session.expires_at_ms <= now_ms:
            _SESSIONS.pop(session_id, None)
            session = None
        if session is not None:
            return session

    if fresh_session:
        return None

    candidates = [
        session
        for session in _SESSIONS.values()
        if session.expires_at_ms > now_ms
        and (
            bool(speaker_id and session.speaker_id == speaker_id)
            or bool(camera_id and session.camera_id == camera_id)
        )
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda session: session.updated_at_ms)


def _create_session(
    *,
    domain: LifeDomain,
    payload: LifeVoiceCommandPayload,
    now_ms: int,
) -> _VoiceSession:
    session = _VoiceSession(
        session_id=f"life_voice_{uuid4().hex}",
        domain=domain,
        speaker_id=payload.speaker_id,
        camera_id=payload.camera_id,
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
        expires_at_ms=now_ms + SESSION_TTL_MS,
    )
    _SESSIONS[session.session_id] = session
    return session


def _is_duplicate_turn(
    session: _VoiceSession | None,
    text: str,
    now_ms: int,
    has_visual_input: bool,
) -> bool:
    if session is None or has_visual_input:
        return False
    return (
        text == session.last_text
        and now_ms - session.last_text_at_ms < DUPLICATE_SUPPRESS_MS
    )


def _remember_turn(session: _VoiceSession, text: str, now_ms: int) -> None:
    session.turn_count += 1
    session.last_text = text
    session.last_text_at_ms = now_ms
    session.updated_at_ms = now_ms
    session.expires_at_ms = now_ms + SESSION_TTL_MS


def _ignored_response(text_trigger: dict[str, Any]) -> dict[str, Any]:
    return {
        "matched": False,
        "session_id": None,
        "session_active": False,
        "domain": None,
        "action": "ignored",
        "needs_visual_capture": False,
        "camera_request": None,
        "trigger": None,
        "broadcast_text": None,
        "speaker_request": None,
        "used_last_context": False,
        "context_cache": _empty_context_cache(),
        "turn_count": 0,
        "reason": text_trigger["reason"],
    }


def _duplicate_response(session: _VoiceSession) -> dict[str, Any]:
    return {
        "matched": True,
        "session_id": session.session_id,
        "session_active": True,
        "domain": session.domain,
        "action": "duplicate_ignored",
        "needs_visual_capture": False,
        "camera_request": None,
        "trigger": None,
        "broadcast_text": None,
        "speaker_request": None,
        "used_last_context": False,
        "context_cache": _context_cache_summary(
            session,
            _now_ms(),
            hit=False,
            refresh_reason="duplicate_voice_command",
        ),
        "turn_count": session.turn_count,
        "reason": "Duplicate voice command suppressed inside the active session.",
    }


def _camera_response(
    session: _VoiceSession,
    payload: LifeVoiceCommandPayload,
    *,
    reason: str,
    now_ms: int,
) -> dict[str, Any]:
    session.camera_id = payload.camera_id or session.camera_id
    return {
        "matched": True,
        "session_id": session.session_id,
        "session_active": True,
        "domain": session.domain,
        "action": "awaiting_visual_capture",
        "needs_visual_capture": True,
        "camera_request": _camera_request(session, payload, reason=reason),
        "trigger": None,
        "broadcast_text": None,
        "speaker_request": None,
        "used_last_context": False,
        "context_cache": _context_cache_summary(
            session,
            now_ms,
            hit=False,
            refresh_reason=reason,
            source_type="camera_required",
        ),
        "turn_count": session.turn_count,
        "reason": (
            "The active voice session needs one short camera clip before "
            "running the life agent."
        ),
    }


def _responded_response(
    session: _VoiceSession,
    *,
    trigger_data: dict[str, Any],
    payload: LifeVoiceCommandPayload,
    text: str,
    now_ms: int,
) -> dict[str, Any]:
    broadcast_text = _broadcast_text_for_trigger(session.domain, trigger_data)
    _remember_turn(session, text, now_ms)
    session.last_trigger = trigger_data
    session.last_broadcast_text = broadcast_text
    session.last_context_at_ms = now_ms
    session.last_context_source_id = _context_source_id(trigger_data, payload)
    session.last_context_source_type = _context_source_type(trigger_data, payload)
    return {
        "matched": True,
        "session_id": session.session_id,
        "session_active": True,
        "domain": session.domain,
        "action": "responded",
        "needs_visual_capture": False,
        "camera_request": None,
        "trigger": trigger_data,
        "broadcast_text": broadcast_text,
        "speaker_request": _speaker_request(session, payload, broadcast_text),
        "used_last_context": False,
        "context_cache": _context_cache_summary(
            session,
            now_ms,
            hit=False,
            refresh_reason=_context_refresh_reason(payload),
        ),
        "turn_count": session.turn_count,
        "reason": "Life-agent recommendation is ready for speaker playback.",
    }


def _context_response(
    session: _VoiceSession,
    payload: LifeVoiceCommandPayload,
    *,
    text: str,
    now_ms: int,
) -> dict[str, Any]:
    last_text = session.last_broadcast_text or _NO_CONTEXT_MESSAGE
    broadcast_text = f"{_CONTEXT_PREFIX}{last_text}"
    _remember_turn(session, text, now_ms)
    cache_hit = session.last_context_at_ms > 0 and session.last_trigger is not None
    return {
        "matched": True,
        "session_id": session.session_id,
        "session_active": True,
        "domain": session.domain,
        "action": "responded",
        "needs_visual_capture": False,
        "camera_request": None,
        "trigger": session.last_trigger,
        "broadcast_text": broadcast_text,
        "speaker_request": _speaker_request(session, payload, broadcast_text),
        "used_last_context": True,
        "context_cache": _context_cache_summary(
            session,
            now_ms,
            hit=cache_hit,
        ),
        "turn_count": session.turn_count,
        "reason": "Follow-up answered from active session context.",
    }


def _camera_request(
    session: _VoiceSession,
    payload: LifeVoiceCommandPayload,
    *,
    reason: str,
) -> dict[str, Any]:
    duration_ms = min(
        max(payload.camera_duration_ms, MIN_CAMERA_DURATION_MS),
        MAX_CAMERA_DURATION_MS,
    )
    return {
        "camera_id": payload.camera_id or session.camera_id,
        "channel": payload.camera_channel,
        "duration_ms": duration_ms,
        "reason": reason,
        "submit_endpoint": "/api/life/voice-command",
        "session_id": session.session_id,
    }


def _speaker_request(
    session: _VoiceSession,
    payload: LifeVoiceCommandPayload,
    message: str | None,
) -> dict[str, Any] | None:
    if not message:
        return None
    return {
        "channel": "xiaomi_speaker",
        "preferred_device_id": payload.speaker_id or session.speaker_id,
        "message": message,
        "requires_ack": False,
    }


def _broadcast_text_for_trigger(
    domain: LifeDomain,
    trigger_data: dict[str, Any],
) -> str | None:
    if domain == "outfit":
        return trigger_data.get("outfit_broadcast_text")
    return trigger_data.get("cooking_broadcast_text")


def _requires_followup_capture(text: str) -> bool:
    normalized = text.strip().lower()
    return any(term in normalized for term in _FOLLOWUP_CAPTURE_TERMS)


def _empty_context_cache() -> dict[str, Any]:
    return {
        "hit": False,
        "domain": None,
        "source_type": None,
        "source_id": None,
        "observed_at_ms": None,
        "age_ms": None,
        "expires_in_ms": None,
        "ttl_ms": SESSION_TTL_MS,
        "refresh_reason": None,
    }


def _context_cache_summary(
    session: _VoiceSession,
    now_ms: int,
    *,
    hit: bool,
    refresh_reason: str | None = None,
    source_type: str | None = None,
) -> dict[str, Any]:
    observed_at_ms = session.last_context_at_ms or None
    age_ms = None
    if observed_at_ms is not None:
        age_ms = max(0, now_ms - observed_at_ms)
    expires_in_ms = max(0, session.expires_at_ms - now_ms)
    return {
        "hit": hit,
        "domain": session.domain,
        "source_type": source_type or session.last_context_source_type,
        "source_id": session.last_context_source_id,
        "observed_at_ms": observed_at_ms,
        "age_ms": age_ms,
        "expires_in_ms": expires_in_ms,
        "ttl_ms": SESSION_TTL_MS,
        "refresh_reason": refresh_reason,
    }


def _context_source_type(
    trigger_data: dict[str, Any],
    payload: LifeVoiceCommandPayload,
) -> str:
    if (
        payload.clip_base64
        or payload.mimo_payload
        or trigger_data.get("used_visual_input")
    ):
        return "visual_result"
    return "inventory_result"


def _context_refresh_reason(payload: LifeVoiceCommandPayload) -> str | None:
    if payload.clip_base64 or payload.mimo_payload:
        return "visual_input"
    return None


def _context_source_id(
    trigger_data: dict[str, Any],
    payload: LifeVoiceCommandPayload,
) -> str | None:
    return (
        _mimo_payload_source_id(payload.mimo_payload)
        or payload.source_id
        or _dict_str(trigger_data.get("history"), "source_id")
        or _dict_str(trigger_data, "source_id")
    )


def _mimo_payload_source_id(payload: dict[str, Any] | str | None) -> str | None:
    if payload is None:
        return None
    if isinstance(payload, dict):
        return _normalized_str(payload.get("source_id"))
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return _normalized_str(parsed.get("source_id"))


def _dict_str(value: Any, key: str) -> str | None:
    if not isinstance(value, dict):
        return None
    return _normalized_str(value.get(key))


def _normalized_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _with_latency(response: dict[str, Any], started_at: float) -> dict[str, Any]:
    duration_ms = max(0, int((time.perf_counter() - started_at) * 1000))
    context_cache = response.get("context_cache")
    cache_hit = False
    visual_refresh_reason = None
    if isinstance(context_cache, dict):
        cache_hit = context_cache.get("hit") is True
        reason = context_cache.get("refresh_reason")
        if isinstance(reason, str) and reason:
            visual_refresh_reason = reason
    response["latency"] = {
        "trigger_detect_latency_ms": 0,
        "answer_latency_ms": duration_ms,
        "total_turn_latency_ms": duration_ms,
        "cache_hit": cache_hit,
        "visual_refresh_reason": visual_refresh_reason,
    }
    return response
