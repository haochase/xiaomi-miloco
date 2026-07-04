# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Visual observation compatibility layer for life-agent live inputs."""

from __future__ import annotations

import base64
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

VisualSourceType = Literal[
    "short_clip",
    "snapshot",
    "sampled_frame",
    "stream",
    "manual_payload",
]
VisualMediaFormat = Literal["mp4", "jpeg", "png", "json", "none"]


class VisualObservationError(ValueError):
    """Raised when a live visual observation cannot be normalized safely."""


class VisualSampling(BaseModel):
    fps: float | None = Field(default=None, gt=0)
    duration_seconds: float | None = Field(default=None, gt=0)
    frame_index: int | None = Field(default=None, ge=0)


class VisualObservation(BaseModel):
    """Normalized visual input, independent from the current clip-only path."""

    source_id: str
    source_type: VisualSourceType
    media_format: VisualMediaFormat = "none"
    content_base64: str | None = None
    mimo_payload: dict[str, Any] | str | None = None
    prompt: str | None = None
    captured_at: str | None = None
    observed_at: str | None = None
    sampling: VisualSampling = Field(default_factory=VisualSampling)

    @field_validator("source_id")
    @classmethod
    def _strip_source_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("source_id must not be blank")
        return value

    @field_validator("prompt", "captured_at", "observed_at")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("content_base64")
    @classmethod
    def _normalize_content_base64(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if value.startswith("data:") and "," in value:
            value = value.split(",", 1)[1]
        if not value:
            return None
        try:
            base64.b64decode(value, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("content_base64 must be valid base64") from exc
        return value

    @model_validator(mode="after")
    def _validate_source_payload(self) -> "VisualObservation":
        if self.source_type == "manual_payload":
            if self.mimo_payload is None:
                raise ValueError("manual_payload observations require mimo_payload")
            if self.content_base64 is not None:
                raise ValueError("manual_payload observations must not include media")
            return self

        if self.source_type == "stream":
            if self.content_base64 is not None:
                raise ValueError(
                    "stream observations must use metadata, not media blobs"
                )
            return self

        if self.content_base64 is None:
            raise ValueError(f"{self.source_type} observations require content_base64")
        return self


def observation_from_live_request(
    *,
    source_id: str,
    prompt: str,
    clip_base64: str | None,
    mimo_payload: dict[str, Any] | str | None,
) -> VisualObservation:
    """Convert the current live-demo request shape into a future-proof observation."""
    try:
        if mimo_payload is not None:
            return VisualObservation(
                source_id=source_id,
                source_type="manual_payload",
                media_format="json",
                prompt=prompt,
                mimo_payload=mimo_payload,
            )
        return VisualObservation(
            source_id=source_id,
            source_type="short_clip",
            media_format="mp4",
            content_base64=clip_base64,
            prompt=prompt,
        )
    except ValueError as exc:
        raise VisualObservationError(str(exc)) from exc
