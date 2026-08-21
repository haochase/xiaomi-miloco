# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the Xiaomi Miloco License Agreement.

"""Low-sensitivity audit facts for bounded Outfit visual reviews."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
