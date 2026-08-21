# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the Xiaomi Miloco License Agreement.

"""Low-sensitivity audit facts for bounded Outfit visual reviews."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from miloco.plugins.audit import (
    AuditEventWriter,
    HostAuditEvent,
    VersionedHmacDigestor,
)

AuditStage = Literal[
    "admitted",
    "capture",
    "provider",
    "cleanup",
    "completed",
    "rejected",
]
AuditTriggerType = Literal["single_frame", "short_clip"]
AuditBudgetOutcome = Literal["allowed", "rejected"]
AuditStatus = Literal[
    "completed",
    "rejected",
    "capture_failed",
    "provider_failed",
    "cleanup_failed",
]


class VisualReviewAuditRecord(BaseModel):
    """Safe counters and digests; no raw media, owner, prompt or token values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id_digest: str = Field(min_length=16, max_length=16)
    device_id_digest: str = Field(min_length=16, max_length=16)
    stage: AuditStage
    trigger_type: AuditTriggerType
    frame_count: int = Field(ge=0, le=5)
    budget_outcome: AuditBudgetOutcome
    status: AuditStatus
    error_code: str | None = Field(default=None, min_length=1)
    elapsed_ms: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    video_tokens: int = Field(ge=0)
    provider_call_count: int = Field(default=0, ge=0, le=1, strict=True)
    usage_complete: bool = Field(default=False, strict=True)


class VisualHostAuditAdapter:
    """Convert transient Outfit visual digests into generic persistent HMAC facts."""

    def __init__(
        self,
        *,
        digestor: VersionedHmacDigestor,
        writer: AuditEventWriter,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self._digestor = digestor
        self._writer = writer
        self._clock_ms = clock_ms or _now_ms

    async def record_visual_review(self, record: VisualReviewAuditRecord) -> None:
        await self._writer.write(
            HostAuditEvent(
                request_event_digest=self._digestor.digest_request(
                    record.request_id_digest
                ),
                device_digest=self._digestor.digest_device(record.device_id_digest),
                flow="visual",
                stage=record.stage,
                status=record.status,
                error_code=record.error_code,
                elapsed_ms=record.elapsed_ms,
                frame_count=record.frame_count,
                provider_call_count=record.provider_call_count,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                video_tokens=record.video_tokens,
                total_tokens=(
                    record.input_tokens + record.output_tokens + record.video_tokens
                ),
                usage_complete=record.usage_complete,
                created_at_ms=self._clock_ms(),
            )
        )


def build_visual_review_audit_record(
    *,
    request_id: str,
    device_id: str,
    stage: AuditStage,
    trigger_type: AuditTriggerType,
    frame_count: int,
    budget_outcome: AuditBudgetOutcome,
    status: AuditStatus,
    error_code: str | None,
    elapsed_ms: int,
    input_tokens: int,
    output_tokens: int,
    video_tokens: int,
    provider_call_count: int = 0,
    usage_complete: bool = False,
) -> VisualReviewAuditRecord:
    """Build one bounded audit record without retaining sensitive identifiers."""

    if not request_id or not device_id:
        raise ValueError("request_id and device_id must be non-empty")
    return VisualReviewAuditRecord(
        request_id_digest=_digest(request_id),
        device_id_digest=_digest(device_id),
        stage=stage,
        trigger_type=trigger_type,
        frame_count=frame_count,
        budget_outcome=budget_outcome,
        status=status,
        error_code=error_code,
        elapsed_ms=elapsed_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        video_tokens=video_tokens,
        provider_call_count=provider_call_count,
        usage_complete=usage_complete,
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
