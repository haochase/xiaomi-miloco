# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the Xiaomi Miloco License Agreement.

"""Best-effort aggregation of bounded host audit usage facts."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from miloco.plugins.audit import AuditFlow, HostAuditEvent

USAGE_TIMEZONE = "Asia/Shanghai"
USAGE_RETENTION_DAYS = 90
_ZONE = ZoneInfo(USAGE_TIMEZONE)
_LOGGER = logging.getLogger(__name__)

UsageProviderCategory = Literal["voice_provider", "vision_provider"]
_PROVIDER_CATEGORY_BY_FLOW: dict[AuditFlow, UsageProviderCategory] = {
    "voice": "voice_provider",
    "visual": "vision_provider",
}


class SanitizedUsageEvent(BaseModel):
    """One irreversible event key and finite usage facts ready for persistence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    local_date: date
    timezone: Literal["Asia/Shanghai"]
    flow: AuditFlow
    provider_category: UsageProviderCategory
    call_count: int = Field(ge=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    complete: bool


class DailyUsageAggregate(BaseModel):
    """One internal aggregate row keyed by date, zone, flow and category."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    local_date: date
    timezone: Literal["Asia/Shanghai"]
    flow: AuditFlow
    provider_category: UsageProviderCategory
    call_count: int = Field(ge=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    complete: bool


class UsageSnapshot(BaseModel):
    """Privacy-bounded totals exposed by the read-only admin API."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    date: date
    timezone: Literal["Asia/Shanghai"]
    call_count: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_total_tokens: int | None = Field(default=None, ge=0)
    complete: bool

    @model_validator(mode="after")
    def validate_token_visibility(self) -> UsageSnapshot:
        tokens = (
            self.input_tokens,
            self.output_tokens,
            self.estimated_total_tokens,
        )
        if self.complete and any(value is None for value in tokens):
            raise ValueError("complete usage must expose every token total")
        if not self.complete and any(value is not None for value in tokens):
            raise ValueError("incomplete usage must hide every token total")
        return self


class UsageRepositoryPort(Protocol):
    """Persistence operations required by the aggregation service."""

    async def record_usage_event(self, event: SanitizedUsageEvent) -> bool: ...

    async def list_daily_aggregates(
        self,
        *,
        local_date: date,
        timezone: str,
    ) -> tuple[DailyUsageAggregate, ...]: ...

    async def purge_before(self, *, cutoff_date: date) -> int: ...


class UsageAggregationService:
    """Consume single H4 audit events without scanning their source storage."""

    def __init__(
        self,
        *,
        repository: UsageRepositoryPort,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._clock = clock

    async def consume_audit_event(self, event: HostAuditEvent) -> None:
        """Best-effort record one provider-bearing event, then apply retention."""

        if event.provider_call_count > 0:
            local_date = (
                datetime.fromtimestamp(
                    event.created_at_ms / 1_000,
                    tz=UTC,
                )
                .astimezone(_ZONE)
                .date()
            )
            sanitized = SanitizedUsageEvent(
                event_key=_safe_event_key(event),
                local_date=local_date,
                timezone=USAGE_TIMEZONE,
                flow=event.flow,
                provider_category=_PROVIDER_CATEGORY_BY_FLOW[event.flow],
                call_count=event.provider_call_count,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                total_tokens=event.total_tokens,
                complete=event.usage_complete,
            )
            try:
                await self._repository.record_usage_event(sanitized)
            except Exception:
                _LOGGER.warning("usage_record_failed")

        try:
            cutoff = self._local_today() - timedelta(days=USAGE_RETENTION_DAYS)
            await self._repository.purge_before(cutoff_date=cutoff)
        except Exception:
            _LOGGER.warning("usage_purge_failed")

    async def get_today(self) -> UsageSnapshot:
        """Read current local-day totals, hiding all token sums when incomplete."""

        today = self._local_today()
        try:
            rows = await self._repository.list_daily_aggregates(
                local_date=today,
                timezone=USAGE_TIMEZONE,
            )
        except Exception:
            _LOGGER.warning("usage_read_failed")
            return _unavailable_snapshot(today)

        if not rows:
            return _empty_snapshot(today)

        complete = all(row.complete for row in rows)
        return UsageSnapshot(
            date=today,
            timezone=USAGE_TIMEZONE,
            call_count=sum(row.call_count for row in rows),
            input_tokens=(sum(row.input_tokens for row in rows) if complete else None),
            output_tokens=(
                sum(row.output_tokens for row in rows) if complete else None
            ),
            estimated_total_tokens=(
                sum(row.total_tokens for row in rows) if complete else None
            ),
            complete=complete,
        )

    def _local_today(self) -> date:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("usage clock must return an aware datetime")
        return now.astimezone(_ZONE).date()


def _safe_event_key(event: HostAuditEvent) -> str:
    payload = json.dumps(
        {
            "request_event_digest": event.request_event_digest.model_dump(),
            "device_digest": event.device_digest.model_dump(),
            "flow": event.flow,
            "stage": event.stage,
            "status": event.status,
            "error_code": event.error_code,
            "elapsed_ms": event.elapsed_ms,
            "frame_count": event.frame_count,
            "provider_call_count": event.provider_call_count,
            "input_tokens": event.input_tokens,
            "output_tokens": event.output_tokens,
            "video_tokens": event.video_tokens,
            "total_tokens": event.total_tokens,
            "usage_complete": event.usage_complete,
            "created_at_ms": event.created_at_ms,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _empty_snapshot(today: date) -> UsageSnapshot:
    return UsageSnapshot(
        date=today,
        timezone=USAGE_TIMEZONE,
        call_count=0,
        input_tokens=0,
        output_tokens=0,
        estimated_total_tokens=0,
        complete=True,
    )


def _unavailable_snapshot(today: date) -> UsageSnapshot:
    return UsageSnapshot(
        date=today,
        timezone=USAGE_TIMEZONE,
        call_count=0,
        input_tokens=None,
        output_tokens=None,
        estimated_total_tokens=None,
        complete=False,
    )
