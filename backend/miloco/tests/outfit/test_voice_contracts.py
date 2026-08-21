from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from miloco.outfit.voice_contracts import (
    MAX_TRUSTED_SPEECH_AGE_MS,
    OutfitVoiceOutcome,
    SpeechTurnRejected,
    SpeechTurnRejectionReason,
    TrustedSpeechTurn,
    VoiceTurnStatus,
    validate_primary_person_id,
)


def _turn(**overrides: object) -> TrustedSpeechTurn:
    values: dict[str, object] = {
        "event_id": " event-1 ",
        "text": " 给我推荐今天的穿搭 ",
        "source_kind": "official_perception",
        "source_device_id": " speaker-1 ",
        "room_id": " living-room ",
        "observed_at_ms": 1_000_000,
        "received_at_ms": 1_001_000,
        "is_complete": True,
        "speaker": " voice-profile-7 ",
    }
    values.update(overrides)
    return TrustedSpeechTurn(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "source_kind",
    ["official_perception", "authenticated_asr_bridge"],
)
def test_trusted_speech_turn_accepts_only_documented_sources(
    source_kind: str,
) -> None:
    turn = _turn(source_kind=source_kind)

    assert turn.source_kind == source_kind
    assert turn.event_id == "event-1"
    assert turn.text == "给我推荐今天的穿搭"
    assert turn.source_device_id == "speaker-1"
    assert turn.room_id == "living-room"
    assert turn.speaker == "voice-profile-7"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"event_id": "  "}, SpeechTurnRejectionReason.MISSING_EVENT_ID),
        ({"text": "\t"}, SpeechTurnRejectionReason.EMPTY_TEXT),
        ({"source_kind": "web_form"}, SpeechTurnRejectionReason.UNKNOWN_SOURCE),
        ({"is_complete": False}, SpeechTurnRejectionReason.INCOMPLETE),
    ],
)
def test_trusted_speech_turn_rejects_invalid_input(
    overrides: dict[str, object],
    reason: SpeechTurnRejectionReason,
) -> None:
    with pytest.raises(SpeechTurnRejected) as exc_info:
        _turn(**overrides)

    assert exc_info.value.reason is reason


def test_trusted_speech_turn_accepts_freshness_boundary() -> None:
    turn = _turn(
        observed_at_ms=1_000_000,
        received_at_ms=1_000_000 + MAX_TRUSTED_SPEECH_AGE_MS,
    )

    assert turn.received_at_ms - turn.observed_at_ms == MAX_TRUSTED_SPEECH_AGE_MS


def test_trusted_speech_turn_rejects_stale_input() -> None:
    with pytest.raises(SpeechTurnRejected) as exc_info:
        _turn(
            observed_at_ms=1_000_000,
            received_at_ms=1_000_001 + MAX_TRUSTED_SPEECH_AGE_MS,
        )

    assert exc_info.value.reason is SpeechTurnRejectionReason.STALE


@pytest.mark.parametrize(
    ("observed_at_ms", "received_at_ms"),
    [(-1, 1_000), (1_001, 1_000), (True, 1_000)],
)
def test_trusted_speech_turn_rejects_invalid_timestamps(
    observed_at_ms: object,
    received_at_ms: object,
) -> None:
    with pytest.raises(SpeechTurnRejected) as exc_info:
        _turn(
            observed_at_ms=observed_at_ms,
            received_at_ms=received_at_ms,
        )

    assert exc_info.value.reason is SpeechTurnRejectionReason.INVALID_TIMESTAMP


def test_idempotency_key_depends_only_on_stable_source_identity() -> None:
    first = _turn()
    replay = _turn(
        text="不同的转写文本",
        room_id="bedroom",
        observed_at_ms=2_000_000,
        received_at_ms=2_001_000,
        speaker="another-profile",
    )

    assert first.idempotency_key == replay.idempotency_key
    assert first.idempotency_key.startswith("outfit-voice:")
    assert first.idempotency_key != _turn(event_id="event-2").idempotency_key
    assert first.idempotency_key != _turn(source_device_id="speaker-2").idempotency_key


def test_primary_user_must_be_injected_separately_from_speaker_metadata() -> None:
    turn = _turn(speaker="person-guessed-by-asr")

    assert validate_primary_person_id(" primary-user ") == "primary-user"
    assert turn.speaker == "person-guessed-by-asr"
    assert not hasattr(turn, "owner_person_id")

    with pytest.raises(SpeechTurnRejected) as exc_info:
        validate_primary_person_id(" ")

    assert exc_info.value.reason is SpeechTurnRejectionReason.MISSING_PRIMARY_PERSON_ID


def test_contracts_are_immutable_and_statuses_are_typed() -> None:
    turn = _turn()
    outcome = OutfitVoiceOutcome(
        status=VoiceTurnStatus.READY,
        response_text="已为你准备三套库存内穿搭",
    )

    with pytest.raises(FrozenInstanceError):
        turn.text = "changed"
    with pytest.raises(FrozenInstanceError):
        outcome.status = VoiceTurnStatus.FAILED

    assert outcome.status == "ready"
    assert {status.value for status in VoiceTurnStatus} == {
        "ignored",
        "needs_context",
        "ready",
        "insufficient_inventory",
        "failed",
    }
