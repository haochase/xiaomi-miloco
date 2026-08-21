# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Narrow conversion of official perception speech into trusted Outfit input."""

from __future__ import annotations

from miloco.outfit.voice_contracts import TrustedSpeechTurn
from miloco.perception.types import Speech


def trusted_turn_from_official_speech(
    speech: Speech,
    *,
    event_id: str,
    observed_at_ms: int,
    received_at_ms: int,
) -> TrustedSpeechTurn | None:
    """Return only complete, directed official speech; never infer the owner."""

    if not speech.needs_response or not speech.is_complete:
        return None
    return TrustedSpeechTurn(
        event_id=event_id,
        text=speech.content,
        source_kind="official_perception",
        source_device_id=_source_device_id(speech),
        room_id=speech.room_name,
        observed_at_ms=observed_at_ms,
        received_at_ms=received_at_ms,
        is_complete=True,
        speaker=speech.speaker,
    )


def _source_device_id(speech: Speech) -> str | None:
    return speech.source_device_ids[0] if speech.source_device_ids else None
