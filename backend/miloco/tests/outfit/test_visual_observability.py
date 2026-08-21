# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Privacy contract for synthetic visual-review audit records."""

import hashlib
import json

import pytest
from miloco.outfit.visual_observability import (
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
    }
    values[field] = value

    with pytest.raises(ValueError):
        build_visual_review_audit_record(**values)
