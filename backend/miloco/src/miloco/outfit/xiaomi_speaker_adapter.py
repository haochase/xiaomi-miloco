# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Single-device Xiaomi speaker adapter for literal Outfit voice playback."""

from __future__ import annotations

from typing import Literal, Protocol


class XiaomiSpeakerActionPort(Protocol):
    """Host-owned MIoT action resolver with no semantic directive escape hatch."""

    async def call_action(
        self,
        *,
        device_id: str,
        action_name: Literal["play-text"],
        params: tuple[str, ...],
    ) -> None: ...


class SpeakerTargetMismatchError(ValueError):
    """The voice service attempted to address a speaker outside its configuration."""


class XiaomiSpeakerAdapter:
    """Send literal text through the configured Xiaomi speaker only once per call.

    Idempotency and timeout behavior remain owned by ``VoiceDeliveryService``;
    this adapter deliberately does not retry or translate text into a directive.
    """

    def __init__(
        self,
        action_port: XiaomiSpeakerActionPort,
        *,
        speaker_device_id: str,
    ) -> None:
        normalized_device_id = speaker_device_id.strip()
        if not normalized_device_id:
            raise ValueError("speaker_device_id is required")
        self._action_port = action_port
        self._speaker_device_id = normalized_device_id

    async def play_text(
        self,
        *,
        device_id: str,
        text: str,
        idempotency_key: str,
    ) -> None:
        """Forward one literal text action to the configured speaker device."""

        del idempotency_key
        if device_id != self._speaker_device_id:
            raise SpeakerTargetMismatchError(
                "speaker target does not match configuration"
            )

        normalized_text = text.strip()
        if not normalized_text:
            raise ValueError("text is required")

        await self._action_port.call_action(
            device_id=self._speaker_device_id,
            action_name="play-text",
            params=(normalized_text,),
        )
