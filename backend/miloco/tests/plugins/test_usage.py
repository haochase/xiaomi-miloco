# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the Xiaomi Miloco License Agreement.

"""Host-audit to daily-usage aggregation contracts."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import pytest
from miloco.plugins.audit import HostAuditEvent, VersionedHmacDigestor
from miloco.plugins.usage import (
    USAGE_TIMEZONE,
    DailyUsageAggregate,
    SanitizedUsageEvent,
    UsageAggregationService,
)


def _audit_event(
    *,
    flow: str = "visual",
    provider_call_count: int = 1,
    input_tokens: int = 8,
    output_tokens: int = 3,
    video_tokens: int = 2,
    usage_complete: bool = True,
    created_at_ms: int = 1_767_268_799_999,
) -> HostAuditEvent:
    digestor = VersionedHmacDigestor(key=b"k" * 32, key_version="audit-v1")
    return HostAuditEvent(
        request_event_digest=digestor.digest_request("safe-request-pre-digest"),
        device_digest=digestor.digest_device("safe-device-pre-digest"),
        flow=flow,
        stage="completed",
        status="completed" if flow == "visual" else "ready",
        error_code=None,
        elapsed_ms=12,
        frame_count=1 if flow == "visual" else 0,
        provider_call_count=provider_call_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        video_tokens=video_tokens,
        total_tokens=input_tokens + output_tokens + video_tokens,
        usage_complete=usage_complete,
        created_at_ms=created_at_ms,
    )


class _RecordingRepository:
    def __init__(
        self,
        *,
        record_error: Exception | None = None,
        purge_error: Exception | None = None,
        read_error: Exception | None = None,
    ) -> None:
        self.record_error = record_error
        self.purge_error = purge_error
        self.read_error = read_error
        self.events: list[SanitizedUsageEvent] = []
        self.cutoffs: list[date] = []
        self.reads: list[tuple[date, str]] = []

    async def record_usage_event(self, event: SanitizedUsageEvent) -> bool:
        if self.record_error is not None:
            raise self.record_error
        self.events.append(event)
        return True

    async def list_daily_aggregates(
        self,
        *,
        local_date: date,
        timezone: str,
    ) -> tuple[DailyUsageAggregate, ...]:
        self.reads.append((local_date, timezone))
        if self.read_error is not None:
            raise self.read_error
        return ()

    async def purge_before(self, *, cutoff_date: date) -> int:
        self.cutoffs.append(cutoff_date)
        if self.purge_error is not None:
            raise self.purge_error
        return 0


@pytest.mark.asyncio
async def test_service_uses_shanghai_calendar_boundary_and_ignores_zero_calls() -> None:
    repository = _RecordingRepository()
    service = UsageAggregationService(
        repository=repository,
        clock=lambda: datetime(2026, 4, 1, tzinfo=UTC),
    )
    before_midnight = int(
        datetime(2026, 1, 1, 15, 59, 59, 999000, tzinfo=UTC).timestamp() * 1_000
    )
    at_midnight = int(datetime(2026, 1, 1, 16, 0, 0, tzinfo=UTC).timestamp() * 1_000)

    await service.consume_audit_event(_audit_event(created_at_ms=before_midnight))
    await service.consume_audit_event(_audit_event(created_at_ms=at_midnight))
    await service.consume_audit_event(
        _audit_event(
            flow="voice",
            provider_call_count=0,
            input_tokens=0,
            output_tokens=0,
            video_tokens=0,
        )
    )

    assert [event.local_date for event in repository.events] == [
        date(2026, 1, 1),
        date(2026, 1, 2),
    ]
    assert all(event.timezone == USAGE_TIMEZONE for event in repository.events)
    assert all(event.flow == "visual" for event in repository.events)
    assert all(
        event.provider_category == "vision_provider" for event in repository.events
    )
    assert repository.cutoffs == [
        date(2026, 1, 1),
        date(2026, 1, 1),
        date(2026, 1, 1),
    ]


@pytest.mark.asyncio
async def test_service_builds_deterministic_safe_event_and_exact_retention_cutoff() -> (
    None
):
    repository = _RecordingRepository()
    service = UsageAggregationService(
        repository=repository,
        clock=lambda: datetime(2026, 4, 1, 16, 0, tzinfo=UTC),
    )
    event = _audit_event(input_tokens=0, output_tokens=0, video_tokens=0)

    await service.consume_audit_event(event)
    await service.consume_audit_event(event)

    first, replay = repository.events
    assert first == replay
    assert len(first.event_key) == 64
    assert event.request_event_digest.digest not in first.model_dump_json()
    assert event.device_digest.digest not in first.model_dump_json()
    assert first.call_count == 1
    assert first.input_tokens == 0
    assert first.output_tokens == 0
    assert first.total_tokens == 0
    assert first.complete is True
    assert repository.cutoffs == [date(2026, 1, 2), date(2026, 1, 2)]


@pytest.mark.asyncio
async def test_service_hides_partial_tokens_and_isolates_repository_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    aggregate = DailyUsageAggregate(
        local_date=date(2026, 4, 2),
        timezone=USAGE_TIMEZONE,
        flow="visual",
        provider_category="vision_provider",
        call_count=2,
        input_tokens=13,
        output_tokens=5,
        total_tokens=21,
        complete=False,
    )
    repository = _RecordingRepository(purge_error=RuntimeError("private purge"))

    async def _list_daily_aggregates(
        *,
        local_date: date,
        timezone: str,
    ) -> tuple[DailyUsageAggregate, ...]:
        repository.reads.append((local_date, timezone))
        return (aggregate,)

    repository.list_daily_aggregates = _list_daily_aggregates  # type: ignore[method-assign]
    service = UsageAggregationService(
        repository=repository,
        clock=lambda: datetime(2026, 4, 2, 1, 0, tzinfo=UTC),
    )

    with caplog.at_level(logging.WARNING, logger="miloco.plugins.usage"):
        await service.consume_audit_event(_audit_event())
        snapshot = await service.get_today()

    assert snapshot.model_dump() == {
        "date": date(2026, 4, 2),
        "timezone": USAGE_TIMEZONE,
        "call_count": 2,
        "input_tokens": None,
        "output_tokens": None,
        "estimated_total_tokens": None,
        "complete": False,
    }
    assert [record.getMessage() for record in caplog.records] == ["usage_purge_failed"]
    assert "private purge" not in caplog.text

    failing_repository = _RecordingRepository(
        record_error=RuntimeError("private insert"),
        read_error=RuntimeError("private read"),
    )
    failing = UsageAggregationService(
        repository=failing_repository,
        clock=lambda: datetime(2026, 4, 2, tzinfo=UTC),
    )
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="miloco.plugins.usage"):
        await failing.consume_audit_event(_audit_event())
        empty = await failing.get_today()

    assert failing_repository.cutoffs == [date(2026, 1, 2)]
    assert empty.call_count == 0
    assert empty.input_tokens is None
    assert empty.output_tokens is None
    assert empty.estimated_total_tokens is None
    assert empty.complete is False
    assert [record.getMessage() for record in caplog.records] == [
        "usage_record_failed",
        "usage_read_failed",
    ]
    assert "private" not in caplog.text
