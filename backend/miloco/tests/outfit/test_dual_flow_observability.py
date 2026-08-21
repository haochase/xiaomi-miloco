# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Contract-only fake host sink for bounded voice and visual observations."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from miloco.outfit.visual_observability import (
    VisualReviewAuditRecord,
    build_visual_review_audit_record,
)
from miloco.outfit.voice_observability import (
    VoiceTurnAuditRecord,
    build_voice_turn_audit_record,
)


@dataclass
class FakeHostAuditSink:
    voice_records: list[VoiceTurnAuditRecord] = field(default_factory=list)
    visual_records: list[VisualReviewAuditRecord] = field(default_factory=list)

    async def record_voice_turn(self, record: VoiceTurnAuditRecord) -> None:
        self.voice_records.append(record)

    async def record_visual_review(self, record: VisualReviewAuditRecord) -> None:
        self.visual_records.append(record)


@pytest.mark.asyncio
async def test_one_fake_host_sink_accepts_both_bounded_flow_records() -> None:
    sink = FakeHostAuditSink()
    voice = build_voice_turn_audit_record(
        event_id="voice-event-1",
        source_device_id="speaker-1",
        stage="completed",
        status="ready",
        delivery_state="delivered",
        error_code=None,
        elapsed_ms=12,
        input_tokens=0,
        output_tokens=0,
    )
    visual = build_visual_review_audit_record(
        request_id="visual-request-1",
        device_id="camera-1",
        stage="completed",
        trigger_type="single_frame",
        frame_count=1,
        budget_outcome="allowed",
        status="completed",
        error_code=None,
        elapsed_ms=19,
        input_tokens=0,
        output_tokens=0,
        video_tokens=0,
    )

    await sink.record_voice_turn(voice)
    await sink.record_visual_review(visual)

    assert sink.voice_records == [voice]
    assert sink.visual_records == [visual]
    payload = voice.model_dump_json() + visual.model_dump_json()
    assert "voice-event-1" not in payload
    assert "speaker-1" not in payload
    assert "visual-request-1" not in payload
    assert "camera-1" not in payload
