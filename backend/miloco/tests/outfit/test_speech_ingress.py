# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Trusted Outfit mapping for official perception speech evidence."""

from miloco.outfit.speech_ingress import trusted_turn_from_official_speech
from miloco.perception.types import Speech


def _speech(*, needs_response: bool = True, is_complete: bool = True) -> Speech:
    return Speech(
        needs_response=needs_response,
        speaker="untrusted-display-name",
        content="今天客户会议怎么穿",
        is_complete=is_complete,
        room_name="living-room",
        source_device_ids=["camera-device-1"],
    )


def test_official_complete_response_speech_maps_to_trusted_turn() -> None:
    turn = trusted_turn_from_official_speech(
        _speech(),
        event_id="perception-event-1",
        observed_at_ms=1_700_000_000_000,
        received_at_ms=1_700_000_000_100,
    )

    assert turn is not None
    assert turn.event_id == "perception-event-1"
    assert turn.text == "今天客户会议怎么穿"
    assert turn.source_kind == "official_perception"
    assert turn.source_device_id == "camera-device-1"
    assert turn.room_id == "living-room"
    assert turn.speaker == "untrusted-display-name"


def test_official_speech_without_response_intent_is_dropped() -> None:
    assert (
        trusted_turn_from_official_speech(
            _speech(needs_response=False),
            event_id="perception-event-1",
            observed_at_ms=1_700_000_000_000,
            received_at_ms=1_700_000_000_100,
        )
        is None
    )


def test_incomplete_official_speech_is_dropped_before_outfit_handling() -> None:
    assert (
        trusted_turn_from_official_speech(
            _speech(is_complete=False),
            event_id="perception-event-1",
            observed_at_ms=1_700_000_000_000,
            received_at_ms=1_700_000_000_100,
        )
        is None
    )
