# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Owner-scoped persistence for once-only Outfit voice turns."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum

from miloco.outfit.storage import OutfitStorage
from miloco.outfit.voice_contracts import TrustedSpeechTurn, VoiceTurnStatus


class VoiceDeliveryState(StrEnum):
    """The observed delivery state for one terminal voice outcome."""

    PENDING = "pending"
    NOT_ATTEMPTED = "not_attempted"
    DELIVERED = "delivered"
    FAILED = "failed"
    UNKNOWN = "unknown"


class VoiceEventClaimStatus(StrEnum):
    """Result of atomically claiming one trusted source event."""

    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    REPLAY = "replay"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class VoiceEventRecord:
    """Persisted terminal outcome for one owner-scoped voice event."""

    owner_person_id: str
    idempotency_key: str
    outcome_status: VoiceTurnStatus
    response_text: str | None
    delivery_state: VoiceDeliveryState


@dataclass(frozen=True, slots=True)
class VoiceEventClaim:
    """The action a voice application service may safely take for an event."""

    status: VoiceEventClaimStatus
    record: VoiceEventRecord | None = None


class VoiceEventNotClaimedError(ValueError):
    """Raised when a service tries to complete an unknown voice event."""


class VoiceEventPayloadConflictError(ValueError):
    """Raised when completion does not match the claimed source event."""


class VoiceEventRepository:
    """Persist at-most-once voice event claims without exposing cross-owner data."""

    def __init__(self, storage: OutfitStorage) -> None:
        self._storage = storage
        self._ensure_schema()

    def claim_event(
        self,
        owner_person_id: str,
        turn: TrustedSpeechTurn,
    ) -> VoiceEventClaim:
        """Atomically claim a source event, replay it, or reject a changed payload."""

        owner = _require_owner_person_id(owner_person_id)
        payload_fingerprint = _payload_fingerprint(turn)
        with self._storage.connect() as connection:
            # SQLite serializes competing claims before either caller can emit TTS.
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT
                    payload_fingerprint,
                    processing_state,
                    outcome_status,
                    response_text,
                    delivery_state
                FROM outfit_voice_events
                WHERE owner_person_id = ? AND idempotency_key = ?
                """,
                (owner, turn.idempotency_key),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO outfit_voice_events (
                        owner_person_id,
                        idempotency_key,
                        payload_fingerprint,
                        processing_state,
                        outcome_status,
                        response_text,
                        delivery_state
                    ) VALUES (?, ?, ?, 'in_progress', NULL, NULL, 'pending')
                    """,
                    (owner, turn.idempotency_key, payload_fingerprint),
                )
                return VoiceEventClaim(status=VoiceEventClaimStatus.CLAIMED)

            if row["payload_fingerprint"] != payload_fingerprint:
                return VoiceEventClaim(status=VoiceEventClaimStatus.CONFLICT)
            if row["processing_state"] == "in_progress":
                return VoiceEventClaim(status=VoiceEventClaimStatus.IN_PROGRESS)
            return VoiceEventClaim(
                status=VoiceEventClaimStatus.REPLAY,
                record=_record_from_row(owner, turn.idempotency_key, row),
            )

    def complete_event(
        self,
        owner_person_id: str,
        turn: TrustedSpeechTurn,
        *,
        outcome_status: VoiceTurnStatus,
        response_text: str | None,
        delivery_state: VoiceDeliveryState,
    ) -> None:
        """Persist one terminal result without retrying speaker delivery."""

        owner = _require_owner_person_id(owner_person_id)
        payload_fingerprint = _payload_fingerprint(turn)
        with self._storage.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT payload_fingerprint, processing_state
                FROM outfit_voice_events
                WHERE owner_person_id = ? AND idempotency_key = ?
                """,
                (owner, turn.idempotency_key),
            ).fetchone()
            if row is None:
                raise VoiceEventNotClaimedError("voice event was not claimed")
            if row["payload_fingerprint"] != payload_fingerprint:
                raise VoiceEventPayloadConflictError("voice event payload changed")
            if row["processing_state"] != "in_progress":
                return

            connection.execute(
                """
                UPDATE outfit_voice_events
                SET
                    processing_state = 'completed',
                    outcome_status = ?,
                    response_text = ?,
                    delivery_state = ?
                WHERE owner_person_id = ? AND idempotency_key = ?
                """,
                (
                    outcome_status.value,
                    response_text,
                    delivery_state.value,
                    owner,
                    turn.idempotency_key,
                ),
            )

    def get_completed_event(
        self,
        owner_person_id: str,
        turn: TrustedSpeechTurn,
    ) -> VoiceEventRecord | None:
        """Return a terminal record for one owner without exposing another owner's event."""

        owner = _require_owner_person_id(owner_person_id)
        with self._storage.connect() as connection:
            row = connection.execute(
                """
                SELECT outcome_status, response_text, delivery_state
                FROM outfit_voice_events
                WHERE owner_person_id = ?
                    AND idempotency_key = ?
                    AND processing_state = 'completed'
                """,
                (owner, turn.idempotency_key),
            ).fetchone()
        if row is None:
            return None
        return _record_from_row(owner, turn.idempotency_key, row)

    def _ensure_schema(self) -> None:
        with self._storage.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS outfit_voice_events (
                    owner_person_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    payload_fingerprint TEXT NOT NULL,
                    processing_state TEXT NOT NULL,
                    outcome_status TEXT,
                    response_text TEXT,
                    delivery_state TEXT NOT NULL,
                    PRIMARY KEY (owner_person_id, idempotency_key)
                );
                """
            )


def _payload_fingerprint(turn: TrustedSpeechTurn) -> str:
    """Fingerprint semantic source-event fields while allowing later receive time."""

    payload = json.dumps(
        {
            "event_id": turn.event_id,
            "is_complete": turn.is_complete,
            "observed_at_ms": turn.observed_at_ms,
            "source_device_id": turn.source_device_id,
            "source_kind": turn.source_kind,
            "text": turn.text,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _record_from_row(
    owner_person_id: str,
    idempotency_key: str,
    row: sqlite3.Row,
) -> VoiceEventRecord:
    outcome_status = row["outcome_status"]
    if outcome_status is None:
        raise ValueError("completed voice event is missing an outcome status")
    return VoiceEventRecord(
        owner_person_id=owner_person_id,
        idempotency_key=idempotency_key,
        outcome_status=VoiceTurnStatus(outcome_status),
        response_text=row["response_text"],
        delivery_state=VoiceDeliveryState(row["delivery_state"]),
    )


def _require_owner_person_id(owner_person_id: str) -> str:
    normalized = owner_person_id.strip() if isinstance(owner_person_id, str) else ""
    if not normalized:
        raise ValueError("owner_person_id must not be blank")
    return normalized
