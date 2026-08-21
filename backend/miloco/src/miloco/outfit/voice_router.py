# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Disabled-by-default authenticated ingress for trusted Outfit voice turns."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from miloco.middleware import verify_token
from miloco.outfit.voice_contracts import (
    OutfitVoiceOutcome,
    SpeechTurnRejected,
    TrustedSpeechTurn,
    VoiceTurnStatus,
)


class VoiceTurnHandler(Protocol):
    """Application boundary whose primary owner was fixed during construction."""

    async def handle(self, *, turn: TrustedSpeechTurn) -> OutfitVoiceOutcome: ...


class AuthenticatedVoiceTurnBody(BaseModel):
    """Only bridge evidence; user-controlled owner and source type are forbidden."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=2_000)
    observed_at_ms: int = Field(ge=0)
    room_id: str | None = Field(default=None, max_length=256)
    is_complete: Literal[True]


class AuthenticatedVoiceTurnResponse(BaseModel):
    """Low-sensitivity application outcome returned to the authenticated bridge."""

    status: VoiceTurnStatus
    message: str | None


def create_authenticated_voice_router(
    *,
    voice_service: VoiceTurnHandler,
    enabled: bool = False,
    source_device_id: str | None = None,
    now_ms: Callable[[], int] | None = None,
) -> APIRouter:
    """Create an opt-in bridge router without deriving the primary user from HTTP.

    The returned router deliberately has no routes until both the caller enables
    this integration and supplies at least one configured bridge device. Host
    composition can therefore omit this router without changing ``/health``.
    """

    router = APIRouter()
    configured_source_device_id = _normalized_device_id(source_device_id)
    if not enabled or configured_source_device_id is None:
        return router

    received_at_ms = now_ms or _now_ms

    @router.post(
        "/api/outfit/voice/turn",
        dependencies=[Depends(verify_token)],
        response_model=AuthenticatedVoiceTurnResponse,
    )
    async def submit_authenticated_voice_turn(
        body: AuthenticatedVoiceTurnBody,
    ) -> AuthenticatedVoiceTurnResponse:
        try:
            turn = TrustedSpeechTurn(
                event_id=body.event_id,
                text=body.text,
                source_kind="authenticated_asr_bridge",
                source_device_id=configured_source_device_id,
                room_id=body.room_id,
                observed_at_ms=body.observed_at_ms,
                received_at_ms=received_at_ms(),
                is_complete=body.is_complete,
            )
        except SpeechTurnRejected as exc:
            raise HTTPException(status_code=422, detail=exc.reason.value) from exc

        outcome = await voice_service.handle(turn=turn)
        return AuthenticatedVoiceTurnResponse(
            status=outcome.status,
            message=outcome.response_text,
        )

    return router


def _normalized_device_id(source_device_id: str | None) -> str | None:
    if not isinstance(source_device_id, str):
        return None
    normalized = source_device_id.strip()
    return normalized or None


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
