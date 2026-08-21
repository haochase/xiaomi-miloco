# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Low-sensitivity audit facts for the authenticated Outfit voice flow."""

import pytest
from miloco.outfit.voice_observability import (
    VoiceHostAuditAdapter,
    build_voice_turn_audit_record,
)


def test_voice_audit_record_hashes_identifiers_and_excludes_sensitive_fields() -> None:
    record = build_voice_turn_audit_record(
        event_id="event-1",
        source_device_id="bridge-1",
        stage="completed",
        status="ready",
        delivery_state="delivered",
        error_code=None,
        elapsed_ms=42,
        input_tokens=0,
        output_tokens=0,
    )

    payload = record.model_dump_json()

    assert len(record.event_id_digest) == 16
    assert len(record.source_device_id_digest) == 16
    assert "event-1" not in payload
    assert "bridge-1" not in payload
    assert "owner" not in payload
    assert "ASR" not in payload
    assert "text" not in payload


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stage", "continuous"),
        ("status", "unknown"),
        ("delivery_state", "retrying"),
    ],
)
def test_voice_audit_record_rejects_unknown_enums(field: str, value: str) -> None:
    values = {
        "event_id": "event-1",
        "source_device_id": "bridge-1",
        "stage": "completed",
        "status": "ready",
        "delivery_state": "delivered",
        "error_code": None,
        "elapsed_ms": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    values[field] = value

    with pytest.raises(ValueError):
        build_voice_turn_audit_record(**values)


def test_voice_audit_record_rejects_blank_identifiers() -> None:
    with pytest.raises(ValueError, match="event_id and source_device_id"):
        build_voice_turn_audit_record(
            event_id="",
            source_device_id="bridge-1",
            stage="completed",
            status="ready",
            delivery_state="delivered",
            error_code=None,
            elapsed_ms=0,
            input_tokens=0,
            output_tokens=0,
        )


def test_voice_audit_record_rejects_unknown_error_code() -> None:
    with pytest.raises(ValueError):
        build_voice_turn_audit_record(
            event_id="event-1",
            source_device_id="bridge-1",
            stage="completed",
            status="ready",
            delivery_state="delivered",
            error_code="owner-or-path-leak",
            elapsed_ms=0,
            input_tokens=0,
            output_tokens=0,
        )


class _RecordingAuditWriter:
    def __init__(self) -> None:
        self.events = []

    async def write(self, event) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_voice_host_adapter_hmacs_pre_digests_and_maps_finite_usage() -> None:
    from miloco.plugins.audit import VersionedHmacDigestor

    writer = _RecordingAuditWriter()
    adapter = VoiceHostAuditAdapter(
        digestor=VersionedHmacDigestor(key=b"k" * 32, key_version="audit-v1"),
        writer=writer,
        clock_ms=lambda: 1_700_000_000_000,
    )
    record = build_voice_turn_audit_record(
        event_id="private-event",
        source_device_id="private-speaker",
        stage="completed",
        status="ready",
        delivery_state="delivered",
        error_code=None,
        elapsed_ms=42,
        input_tokens=0,
        output_tokens=0,
    )

    await adapter.record_voice_turn(record)

    assert len(writer.events) == 1
    event = writer.events[0]
    assert event.flow == "voice"
    assert event.provider_call_count == 0
    assert event.usage_complete is True
    assert event.total_tokens == 0
    assert event.created_at_ms == 1_700_000_000_000
    payload = event.model_dump_json()
    assert record.event_id_digest not in payload
    assert record.source_device_id_digest not in payload
    assert "private-event" not in payload
    assert "private-speaker" not in payload
