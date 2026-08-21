# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Generic, privacy-bounded host audit contracts."""

from __future__ import annotations

import hashlib
import hmac
import logging
from collections.abc import Callable
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

AUDIT_RETENTION_MS = 10 * 24 * 60 * 60 * 1_000
_MAX_SQLITE_INTEGER = (1 << 63) - 1
_LOGGER = logging.getLogger(__name__)

AuditFlow = Literal["voice", "visual"]
AuditStage = Literal[
    "recommendation",
    "delivery",
    "completed",
    "replay",
    "admitted",
    "capture",
    "provider",
    "cleanup",
    "rejected",
]
AuditStatus = Literal[
    "ready",
    "needs_context",
    "insufficient_inventory",
    "failed",
    "ignored",
    "completed",
    "rejected",
    "capture_failed",
    "provider_failed",
    "cleanup_failed",
]
AuditErrorCode = Literal[
    "event_in_progress",
    "event_conflict",
    "recommendation_failed",
    "speaker_delivery_failed",
    "explicit_trigger_required",
    "session_expired",
    "concurrent_request_limit",
    "model_call_limit",
    "token_budget_exceeded",
    "usage_unavailable",
    "provider_error_limit",
    "session_start_in_future",
    "session_start_mismatch",
    "capture_timeout",
    "overall_timeout",
    "capture_failed",
    "provider_timeout",
    "provider_failed",
    "temporary_media_cleanup_failed",
    "request_cancelled",
]


class VersionedHmacDigest(BaseModel):
    """Safe key version and fixed-length HMAC-SHA256 output only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key_version: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$",
    )
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class HostAuditEvent(BaseModel):
    """Finite host audit facts without raw IDs, content, paths or provider details."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_event_digest: VersionedHmacDigest
    device_digest: VersionedHmacDigest
    flow: AuditFlow
    stage: AuditStage
    status: AuditStatus
    error_code: AuditErrorCode | None = None
    elapsed_ms: int = Field(ge=0, le=_MAX_SQLITE_INTEGER, strict=True)
    frame_count: int = Field(ge=0, le=5, strict=True)
    provider_call_count: int = Field(ge=0, le=1, strict=True)
    input_tokens: int = Field(ge=0, le=_MAX_SQLITE_INTEGER, strict=True)
    output_tokens: int = Field(ge=0, le=_MAX_SQLITE_INTEGER, strict=True)
    video_tokens: int = Field(ge=0, le=_MAX_SQLITE_INTEGER, strict=True)
    total_tokens: int = Field(ge=0, le=_MAX_SQLITE_INTEGER, strict=True)
    usage_complete: bool = Field(strict=True)
    created_at_ms: int = Field(ge=0, le=_MAX_SQLITE_INTEGER, strict=True)

    @model_validator(mode="after")
    def validate_token_total(self) -> HostAuditEvent:
        if self.total_tokens != (
            self.input_tokens + self.output_tokens + self.video_tokens
        ):
            raise ValueError("total_tokens must equal component token counts")
        return self


class VersionedHmacDigestor:
    """Create domain-separated HMAC-SHA256 digests for host audit persistence."""

    def __init__(self, *, key: bytes, key_version: str) -> None:
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("audit HMAC key must contain at least 32 bytes")
        validated_version = VersionedHmacDigest(
            key_version=key_version,
            digest="0" * 64,
        ).key_version
        self._key = bytes(key)
        self._key_version = validated_version

    def digest_event(self, value: str) -> VersionedHmacDigest:
        return self._digest(namespace="event", value=value)

    def digest_request(self, value: str) -> VersionedHmacDigest:
        return self._digest(namespace="request", value=value)

    def digest_device(self, value: str) -> VersionedHmacDigest:
        return self._digest(namespace="device", value=value)

    def _digest(
        self,
        *,
        namespace: Literal["event", "request", "device"],
        value: str,
    ) -> VersionedHmacDigest:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("audit digest input must not be blank")
        message = b"\0".join(
            (
                b"miloco-host-audit",
                self._key_version.encode("ascii"),
                namespace.encode("ascii"),
                value.encode("utf-8"),
            )
        )
        return VersionedHmacDigest(
            key_version=self._key_version,
            digest=hmac.new(self._key, message, hashlib.sha256).hexdigest(),
        )


class AuditEventRepository(Protocol):
    """Persistence operations required by the best-effort writer."""

    async def insert(self, event: HostAuditEvent) -> None: ...

    async def purge_older_than(self, *, cutoff_ms: int) -> int: ...


class AuditEventWriter(Protocol):
    """Generic async host-owned writer used by domain adapters."""

    async def write(self, event: HostAuditEvent) -> None: ...


class BestEffortAuditWriter:
    """Isolate repository failures and apply strict ten-day retention after insert."""

    def __init__(
        self,
        *,
        repository: AuditEventRepository,
        clock_ms: Callable[[], int],
    ) -> None:
        self._repository = repository
        self._clock_ms = clock_ms

    async def write(self, event: HostAuditEvent) -> None:
        try:
            await self._repository.insert(event)
        except Exception:
            _LOGGER.warning("host_audit_insert_failed")
            return
        try:
            cutoff_ms = self._clock_ms() - AUDIT_RETENTION_MS
            await self._repository.purge_older_than(cutoff_ms=cutoff_ms)
        except Exception:
            _LOGGER.warning("host_audit_purge_failed")
