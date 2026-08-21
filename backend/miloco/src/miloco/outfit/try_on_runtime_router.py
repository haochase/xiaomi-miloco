# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Disabled-by-default authenticated trigger for one user-requested visual review."""

from __future__ import annotations

from collections.abc import Collection
from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from miloco.middleware import verify_token
from miloco.outfit.visual_service import VisualReviewOutcome, VisualReviewStatus


class VisualTriggerHandler(Protocol):
    """Host/application handler that owns snapshot, owner and budget resolution."""

    async def handle_trigger(
        self,
        *,
        trigger_id: str,
        recommendation_id: str,
        device_id: str,
    ) -> VisualReviewOutcome: ...


class VisualTriggerBody(BaseModel):
    """Only the selected recommendation and configured camera may be requested."""

    model_config = ConfigDict(extra="forbid")

    trigger_id: str = Field(min_length=1, max_length=256)
    recommendation_id: str = Field(min_length=1, max_length=256)
    device_id: str = Field(min_length=1, max_length=256)

    @field_validator("trigger_id", "recommendation_id", "device_id", mode="before")
    @classmethod
    def normalize_identifier(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("visual trigger identifiers must not be blank")
        return normalized


class VisualTriggerResponse(BaseModel):
    """Low-sensitivity visual-review result without media or provider details."""

    status: VisualReviewStatus
    error_code: str | None


def create_visual_trigger_router(
    *,
    visual_handler: VisualTriggerHandler,
    enabled: bool = False,
    device_allowlist: Collection[str] = (),
) -> APIRouter:
    """Create an opt-in trigger router without accepting owner or media selectors."""

    router = APIRouter()
    allowed_devices = _normalized_allowlist(device_allowlist)
    if not enabled or not allowed_devices:
        return router

    @router.post(
        "/api/outfit/try-on/review",
        dependencies=[Depends(verify_token)],
        response_model=VisualTriggerResponse,
    )
    async def submit_visual_trigger(
        body: VisualTriggerBody,
    ) -> VisualTriggerResponse:
        if body.device_id not in allowed_devices:
            raise HTTPException(status_code=403, detail="untrusted visual device")

        outcome = await visual_handler.handle_trigger(
            trigger_id=body.trigger_id,
            recommendation_id=body.recommendation_id,
            device_id=body.device_id,
        )
        return VisualTriggerResponse(
            status=outcome.status,
            error_code=outcome.error_code,
        )

    return router


def _normalized_allowlist(device_allowlist: Collection[str]) -> frozenset[str]:
    return frozenset(
        device_id.strip()
        for device_id in device_allowlist
        if isinstance(device_id, str) and device_id.strip()
    )
