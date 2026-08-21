# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Persistence contracts for idempotent Outfit voice events."""

from pathlib import Path

from miloco.outfit.storage import OutfitStorage
from miloco.outfit.voice_contracts import TrustedSpeechTurn, VoiceTurnStatus
from miloco.outfit.voice_event_repo import (
    VoiceDeliveryState,
    VoiceEventClaimStatus,
    VoiceEventRepository,
)


def _repository(tmp_path: Path) -> VoiceEventRepository:
    return VoiceEventRepository(OutfitStorage(tmp_path / "outfit" / "voice-events.db"))


def _turn(*, text: str = "今天开会怎么穿") -> TrustedSpeechTurn:
    return TrustedSpeechTurn(
        event_id="speech-event-1",
        text=text,
        source_kind="official_perception",
        source_device_id="speaker-device-1",
        room_id="living-room",
        observed_at_ms=1_700_000_000_000,
        received_at_ms=1_700_000_000_100,
        is_complete=True,
    )


def test_event_claim_is_once_only_until_completed_then_replays_outcome(
    tmp_path: Path,
) -> None:
    first_repository = _repository(tmp_path)
    second_repository = _repository(tmp_path)
    turn = _turn()

    first_claim = first_repository.claim_event("primary-person", turn)
    duplicate_claim = second_repository.claim_event("primary-person", turn)

    assert first_claim.status is VoiceEventClaimStatus.CLAIMED
    assert duplicate_claim.status is VoiceEventClaimStatus.IN_PROGRESS

    first_repository.complete_event(
        "primary-person",
        turn,
        outcome_status=VoiceTurnStatus.READY,
        response_text="推荐第一套深蓝衬衫搭配黑色长裤和皮鞋。",
        delivery_state=VoiceDeliveryState.DELIVERED,
    )

    replay = second_repository.claim_event("primary-person", turn)

    assert replay.status is VoiceEventClaimStatus.REPLAY
    assert replay.record is not None
    assert replay.record.outcome_status is VoiceTurnStatus.READY
    assert replay.record.delivery_state is VoiceDeliveryState.DELIVERED
    assert replay.record.response_text == "推荐第一套深蓝衬衫搭配黑色长裤和皮鞋。"


def test_event_claim_rejects_changed_payload_for_same_owner_event(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    original_turn = _turn()

    assert repository.claim_event("primary-person", original_turn).status is (
        VoiceEventClaimStatus.CLAIMED
    )

    changed_payload = repository.claim_event(
        "primary-person",
        _turn(text="今天跑步怎么穿"),
    )

    assert changed_payload.status is VoiceEventClaimStatus.CONFLICT


def test_event_claim_keeps_identical_source_event_isolated_per_owner(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    turn = _turn()

    primary_claim = repository.claim_event("primary-person", turn)
    other_claim = repository.claim_event("other-person", turn)

    assert primary_claim.status is VoiceEventClaimStatus.CLAIMED
    assert other_claim.status is VoiceEventClaimStatus.CLAIMED
