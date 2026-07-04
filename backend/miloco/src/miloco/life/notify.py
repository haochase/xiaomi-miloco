# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Notification adapter for life-agent demo outputs."""

from __future__ import annotations

from typing import Literal

import httpx
from pydantic import BaseModel, field_validator, model_validator

from miloco.life.schema import LifeDomain, _reject_absolute_safety_claim_text

LifeNotifyUrgency = Literal["low", "medium", "high"]
LifeNotifyChannel = Literal["pc_speaker", "text"]


class LifeNotifyRequest(BaseModel):
    message: str
    domain: LifeDomain
    urgency: LifeNotifyUrgency = "low"
    requires_ack: bool = False
    pc_speaker_url: str | None = None
    fallback_to_text: bool = True

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value

    @field_validator("pc_speaker_url")
    @classmethod
    def _normalize_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def _reject_absolute_kitchen_claims(self) -> "LifeNotifyRequest":
        if self.domain == "cooking":
            _reject_absolute_safety_claim_text(self.message)
        return self


class LifeNotifyResult(BaseModel):
    channel: LifeNotifyChannel
    delivered: bool
    fallback_text: str | None = None
    requires_ack: bool
    reason: str


def deliver_life_notification(
    request: LifeNotifyRequest,
    *,
    timeout_seconds: float = 2.0,
    transport: httpx.BaseTransport | None = None,
) -> LifeNotifyResult:
    """Send life-agent notification to a mockable channel with text fallback."""
    if not request.pc_speaker_url:
        return _fallback_result(request, "pc_speaker_url not configured")

    try:
        with httpx.Client(timeout=timeout_seconds, transport=transport) as client:
            response = client.post(
                request.pc_speaker_url,
                json={
                    "message": request.message,
                    "domain": request.domain,
                    "urgency": request.urgency,
                    "requires_ack": request.requires_ack,
                },
            )
    except httpx.HTTPError as exc:
        return _fallback_result(request, f"pc_speaker request failed: {exc}")

    if response.status_code >= 400:
        return _fallback_result(request, f"pc_speaker returned {response.status_code}")

    return LifeNotifyResult(
        channel="pc_speaker",
        delivered=True,
        fallback_text=None,
        requires_ack=request.requires_ack,
        reason="delivered",
    )


def _fallback_result(request: LifeNotifyRequest, reason: str) -> LifeNotifyResult:
    return LifeNotifyResult(
        channel="text",
        delivered=False,
        fallback_text=request.message if request.fallback_to_text else None,
        requires_ack=request.requires_ack,
        reason=reason,
    )
