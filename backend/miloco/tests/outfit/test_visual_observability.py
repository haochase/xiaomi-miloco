# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Privacy contract for synthetic visual-review audit records."""

import hashlib
import json

import pytest
from miloco.outfit.visual_observability import (
    VisualHostAuditAdapter,
    VisualReviewAuditRecord,
    build_visual_review_audit_record,
)


def test_audit_record_hashes_identifiers_and_keeps_only_safe_counters() -> None:
    record = build_visual_review_audit_record(
        request_id="private-request-id",
        device_id="private-camera-id",
        stage="completed",
        trigger_type="single_frame",
        frame_count=1,
        budget_outcome="allowed",
        status="completed",
        error_code=None,
        elapsed_ms=125,
        input_tokens=80,
        output_tokens=20,
        video_tokens=0,
        provider_call_count=1,
        usage_complete=True,
    )

    assert isinstance(record, VisualReviewAuditRecord)
    assert (
        record.request_id_digest
        == hashlib.sha256(b"private-request-id").hexdigest()[:16]
    )
    assert (
        record.device_id_digest == hashlib.sha256(b"private-camera-id").hexdigest()[:16]
    )
    assert record.frame_count == 1
    assert record.input_tokens == 80
    assert record.output_tokens == 20
    assert record.video_tokens == 0
    assert record.provider_call_count == 1
    assert record.usage_complete is True
    encoded = json.dumps(record.model_dump())
    assert "private-request-id" not in encoded
    assert "private-camera-id" not in encoded
    assert "owner_person_id" not in encoded
    assert "media_path" not in encoded
    assert "asr_text" not in encoded


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trigger_type", "continuous"),
        ("stage", "unknown"),
        ("budget_outcome", "maybe"),
    ],
)
def test_audit_record_rejects_unbounded_or_continuous_states(
    field: str,
    value: str,
) -> None:
    values: dict[str, object] = {
        "request_id": "request-1",
        "device_id": "camera-1",
        "stage": "completed",
        "trigger_type": "single_frame",
        "frame_count": 1,
        "budget_outcome": "allowed",
        "status": "completed",
        "error_code": None,
        "elapsed_ms": 1,
        "input_tokens": 1,
        "output_tokens": 1,
        "video_tokens": 0,
        "provider_call_count": 1,
        "usage_complete": True,
    }
    values[field] = value

    with pytest.raises(ValueError):
        build_visual_review_audit_record(**values)


def test_complete_zero_token_usage_is_not_inferred_as_missing() -> None:
    record = build_visual_review_audit_record(
        request_id="request-1",
        device_id="camera-1",
        stage="completed",
        trigger_type="single_frame",
        frame_count=1,
        budget_outcome="allowed",
        status="completed",
        error_code=None,
        elapsed_ms=1,
        input_tokens=0,
        output_tokens=0,
        video_tokens=0,
        provider_call_count=1,
        usage_complete=True,
    )

    assert record.provider_call_count == 1
    assert record.usage_complete is True


class _RecordingAuditWriter:
    def __init__(self) -> None:
        self.events = []

    async def write(self, event) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_visual_host_adapter_hmacs_pre_digests_and_preserves_usage_facts() -> (
    None
):
    from miloco.plugins.audit import VersionedHmacDigestor

    writer = _RecordingAuditWriter()
    adapter = VisualHostAuditAdapter(
        digestor=VersionedHmacDigestor(key=b"k" * 32, key_version="audit-v1"),
        writer=writer,
        clock_ms=lambda: 1_700_000_000_000,
    )
    record = build_visual_review_audit_record(
        request_id="private-request",
        device_id="private-camera",
        stage="completed",
        trigger_type="single_frame",
        frame_count=1,
        budget_outcome="allowed",
        status="completed",
        error_code=None,
        elapsed_ms=8,
        input_tokens=0,
        output_tokens=0,
        video_tokens=0,
        provider_call_count=1,
        usage_complete=True,
    )

    await adapter.record_visual_review(record)

    assert len(writer.events) == 1
    event = writer.events[0]
    assert event.flow == "visual"
    assert event.frame_count == 1
    assert event.provider_call_count == 1
    assert event.usage_complete is True
    assert event.total_tokens == 0
    assert event.created_at_ms == 1_700_000_000_000
    payload = event.model_dump_json()
    assert record.request_id_digest not in payload
    assert record.device_id_digest not in payload
    assert "private-request" not in payload
    assert "private-camera" not in payload
