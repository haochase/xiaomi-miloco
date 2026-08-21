# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Low-sensitivity audit facts for bounded Outfit voice turns."""

from __future__ import annotations

import hashlib
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

VoiceAuditStage = Literal["recommendation", "delivery", "completed", "replay"]
VoiceAuditStatus = Literal[
    "ready",
    "needs_context",
    "insufficient_inventory",
    "failed",
    "ignored",
]
VoiceAuditDeliveryState = Literal[
    "delivered",
    "failed",
    "unknown",
    "not_attempted",
    "replayed",
]
VoiceAuditErrorCode = Literal[
    "event_in_progress",
    "event_conflict",
    "recommendation_failed",
    "speaker_delivery_failed",
]

_ABSENT_SOURCE_DEVICE_ID_INPUT = "outfit-voice-source-device-absent"


class VoiceTurnAuditRecord(BaseModel):
    """Safe voice-flow counters and digests without ASR text or owner data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id_digest: str = Field(min_length=16, max_length=16)
    source_device_id_digest: str = Field(min_length=16, max_length=16)
    stage: VoiceAuditStage
    status: VoiceAuditStatus
    delivery_state: VoiceAuditDeliveryState
    error_code: VoiceAuditErrorCode | None = None
    elapsed_ms: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class VoiceTurnAuditPort(Protocol):
    """Host-owned sink for one low-sensitivity voice-flow observation."""

    async def record_voice_turn(self, record: VoiceTurnAuditRecord) -> None: ...


def build_voice_turn_audit_record(
    *,
    event_id: str,
    source_device_id: str | None,
    stage: VoiceAuditStage,
    status: VoiceAuditStatus,
    delivery_state: VoiceAuditDeliveryState,
    error_code: VoiceAuditErrorCode | None,
    elapsed_ms: int,
    input_tokens: int,
    output_tokens: int,
) -> VoiceTurnAuditRecord:
    """Build one bounded audit record without retaining sensitive identifiers."""

    if not event_id or source_device_id == "":
        raise ValueError("event_id and source_device_id must be non-empty")
    source_device_digest_input = (
        source_device_id
        if source_device_id is not None
        else _ABSENT_SOURCE_DEVICE_ID_INPUT
    )
    return VoiceTurnAuditRecord(
        event_id_digest=_digest(event_id),
        source_device_id_digest=_digest(source_device_digest_input),
        stage=stage,
        status=status,
        delivery_state=delivery_state,
        error_code=error_code,
        elapsed_ms=elapsed_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
