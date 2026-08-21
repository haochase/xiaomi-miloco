"""Trusted speech contracts for the Outfit application boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, cast

SpeechSourceKind = Literal["official_perception", "authenticated_asr_bridge"]

MAX_TRUSTED_SPEECH_AGE_MS = 30_000
_ALLOWED_SOURCE_KINDS = frozenset({"official_perception", "authenticated_asr_bridge"})


class VoiceTurnStatus(StrEnum):
    """Typed application outcomes for a trusted voice turn."""

    IGNORED = "ignored"
    NEEDS_CONTEXT = "needs_context"
    READY = "ready"
    INSUFFICIENT_INVENTORY = "insufficient_inventory"
    FAILED = "failed"


class SpeechTurnRejectionReason(StrEnum):
    """Fail-closed reasons that are safe to expose in application telemetry."""

    MISSING_EVENT_ID = "missing_event_id"
    EMPTY_TEXT = "empty_text"
    UNKNOWN_SOURCE = "unknown_source"
    INCOMPLETE = "incomplete"
    INVALID_TIMESTAMP = "invalid_timestamp"
    STALE = "stale"
    MISSING_PRIMARY_PERSON_ID = "missing_primary_person_id"


class SpeechTurnRejected(ValueError):
    """A trusted speech contract rejected input before domain processing."""

    def __init__(self, reason: SpeechTurnRejectionReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


@dataclass(frozen=True, slots=True)
class TrustedSpeechTurn:
    """Complete, fresh speech evidence accepted from an allowed host source.

    ``speaker`` is untrusted audit metadata. The primary user is injected by the
    host separately and is deliberately absent from this input contract.
    """

    event_id: str
    text: str
    source_kind: SpeechSourceKind
    source_device_id: str | None
    room_id: str | None
    observed_at_ms: int
    received_at_ms: int
    is_complete: bool
    speaker: str | None = None

    def __post_init__(self) -> None:
        event_id = self.event_id.strip() if isinstance(self.event_id, str) else ""
        if not event_id:
            raise SpeechTurnRejected(SpeechTurnRejectionReason.MISSING_EVENT_ID)

        text = self.text.strip() if isinstance(self.text, str) else ""
        if not text:
            raise SpeechTurnRejected(SpeechTurnRejectionReason.EMPTY_TEXT)

        if self.source_kind not in _ALLOWED_SOURCE_KINDS:
            raise SpeechTurnRejected(SpeechTurnRejectionReason.UNKNOWN_SOURCE)

        if self.is_complete is not True:
            raise SpeechTurnRejected(SpeechTurnRejectionReason.INCOMPLETE)

        if not _is_valid_timestamp(self.observed_at_ms) or not _is_valid_timestamp(
            self.received_at_ms
        ):
            raise SpeechTurnRejected(SpeechTurnRejectionReason.INVALID_TIMESTAMP)
        if self.observed_at_ms > self.received_at_ms:
            raise SpeechTurnRejected(SpeechTurnRejectionReason.INVALID_TIMESTAMP)
        if self.received_at_ms - self.observed_at_ms > MAX_TRUSTED_SPEECH_AGE_MS:
            raise SpeechTurnRejected(SpeechTurnRejectionReason.STALE)

        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "text", text)
        object.__setattr__(
            self, "source_device_id", _normalize_optional_text(self.source_device_id)
        )
        object.__setattr__(self, "room_id", _normalize_optional_text(self.room_id))
        object.__setattr__(self, "speaker", _normalize_optional_text(self.speaker))
        object.__setattr__(
            self, "source_kind", cast(SpeechSourceKind, self.source_kind)
        )

    @property
    def idempotency_key(self) -> str:
        """Return a stable key based only on the trusted source identity."""

        payload = json.dumps(
            [self.source_kind, self.source_device_id, self.event_id],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"outfit-voice:{digest}"


@dataclass(frozen=True, slots=True)
class OutfitVoiceOutcome:
    """Minimal typed result returned by the future voice application service."""

    status: VoiceTurnStatus
    response_text: str | None = None


def validate_primary_person_id(primary_person_id: str) -> str:
    """Validate the primary user reference injected by the host configuration."""

    normalized = primary_person_id.strip() if isinstance(primary_person_id, str) else ""
    if not normalized:
        raise SpeechTurnRejected(SpeechTurnRejectionReason.MISSING_PRIMARY_PERSON_ID)
    return normalized


def _is_valid_timestamp(value: object) -> bool:
    return type(value) is int and value >= 0


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
