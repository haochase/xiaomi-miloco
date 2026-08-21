# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Narrow speaker delivery boundary for Outfit voice responses."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from miloco.outfit.voice_event_repo import VoiceDeliveryState


class SpeakerTextPort(Protocol):
    """Host-owned literal speaker action; semantic directives are intentionally absent."""

    async def play_text(
        self,
        *,
        device_id: str,
        text: str,
        idempotency_key: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class VoiceDeliveryResult:
    """Typed result of one and only one speaker delivery attempt."""

    state: VoiceDeliveryState


class VoiceDeliveryService:
    """Attempt literal text delivery once and never retry an unknown result."""

    def __init__(
        self,
        speaker: SpeakerTextPort,
        *,
        device_id: str,
        timeout_s: float,
    ) -> None:
        normalized_device_id = device_id.strip() if isinstance(device_id, str) else ""
        if not normalized_device_id:
            raise ValueError("speaker device_id must not be blank")
        if timeout_s <= 0:
            raise ValueError("speaker timeout_s must be positive")

        self._speaker = speaker
        self._device_id = normalized_device_id
        self._timeout_s = timeout_s

    async def deliver_once(
        self,
        *,
        text: str,
        idempotency_key: str,
    ) -> VoiceDeliveryResult:
        """Send one literal text action and classify exceptions without another attempt."""

        try:
            await asyncio.wait_for(
                self._speaker.play_text(
                    device_id=self._device_id,
                    text=text,
                    idempotency_key=idempotency_key,
                ),
                timeout=self._timeout_s,
            )
        except asyncio.TimeoutError:
            return VoiceDeliveryResult(state=VoiceDeliveryState.UNKNOWN)
        except Exception:
            return VoiceDeliveryResult(state=VoiceDeliveryState.FAILED)
        return VoiceDeliveryResult(state=VoiceDeliveryState.DELIVERED)
