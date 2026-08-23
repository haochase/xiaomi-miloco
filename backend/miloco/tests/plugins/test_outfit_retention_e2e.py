# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""End-to-end SQLite retention contracts for the optional Outfit host services."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from miloco.outfit.admin_router import create_outfit_admin_usage_router
from miloco.plugins.audit import (
    AUDIT_RETENTION_MS,
    BestEffortAuditWriter,
    HostAuditEvent,
    VersionedHmacDigestor,
)
from miloco.plugins.audit_repo import AuditRepository
from miloco.plugins.usage import (
    USAGE_RETENTION_DAYS,
    USAGE_TIMEZONE,
    DailyUsageAggregate,
    UsageAggregationService,
    UsageSnapshot,
)
from miloco.plugins.usage_repo import UsageRepository

_SHANGHAI = ZoneInfo(USAGE_TIMEZONE)
_DIGESTOR = VersionedHmacDigestor(key=b"k" * 32, key_version="audit-v1")


def _require_test_bearer(request: Request) -> None:
    if request.headers.get("Authorization") != "Bearer test-token":
        raise HTTPException(status_code=401, detail="invalid test bearer")


def _event(*, label: str, created_at_ms: int) -> HostAuditEvent:
    return HostAuditEvent(
        request_event_digest=_DIGESTOR.digest_request(f"request-{label}"),
        device_digest=_DIGESTOR.digest_device(f"device-{label}"),
        flow="visual",
        stage="completed",
        status="completed",
        error_code=None,
        elapsed_ms=12,
        frame_count=1,
        provider_call_count=1,
        input_tokens=7,
        output_tokens=2,
        video_tokens=1,
        total_tokens=10,
        usage_complete=True,
        created_at_ms=created_at_ms,
    )


def _local_noon_ms(local_date: date) -> int:
    return int(
        datetime(
            local_date.year,
            local_date.month,
            local_date.day,
            12,
            tzinfo=_SHANGHAI,
        ).timestamp()
        * 1_000
    )


def _aggregate(local_date: date) -> DailyUsageAggregate:
    return DailyUsageAggregate(
        local_date=local_date,
        timezone=USAGE_TIMEZONE,
        flow="visual",
        provider_category="vision_provider",
        call_count=1,
        input_tokens=7,
        output_tokens=2,
        total_tokens=10,
        complete=True,
    )


def _seen_event_dates(database_path: Path) -> tuple[str, ...]:
    connection = sqlite3.connect(str(database_path))
    try:
        rows = connection.execute(
            "SELECT local_date FROM usage_seen_events ORDER BY local_date, event_key"
        ).fetchall()
    finally:
        connection.close()
    return tuple(row[0] for row in rows)


def _usage_columns(database_path: Path, table: str) -> tuple[str, ...]:
    connection = sqlite3.connect(str(database_path))
    try:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    finally:
        connection.close()
    return tuple(row[1] for row in rows)


@pytest.mark.asyncio
async def test_audit_writer_keeps_cutoff_and_later_events_after_repository_rebuild(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "audit-retention" / "audit.sqlite"
    assert database_path.is_absolute()
    fixed_now_ms = _local_noon_ms(date(2026, 4, 1))
    cutoff_ms = fixed_now_ms - AUDIT_RETENTION_MS
    repository = AuditRepository(database_path)
    writer = BestEffortAuditWriter(
        repository=repository,
        clock_ms=lambda: fixed_now_ms,
    )

    for event in (
        _event(label="before", created_at_ms=cutoff_ms - 1),
        _event(label="at", created_at_ms=cutoff_ms),
        _event(label="after", created_at_ms=cutoff_ms + 1),
    ):
        await writer.write(event)

    expected_created_at = (cutoff_ms, cutoff_ms + 1)
    assert tuple(event.created_at_ms for event in await repository.list_events()) == (
        expected_created_at
    )

    reopened = AuditRepository(database_path)
    assert tuple(event.created_at_ms for event in await reopened.list_events()) == (
        expected_created_at
    )


@pytest.mark.asyncio
async def test_usage_retention_deduplicates_rebuilds_and_keeps_today_reader_consistent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "usage-retention" / "usage.sqlite"
    assert database_path.is_absolute()
    fixed_now = datetime(2026, 4, 1, 4, tzinfo=UTC)
    today = fixed_now.astimezone(_SHANGHAI).date()
    cutoff = today - timedelta(days=USAGE_RETENTION_DAYS)
    before_cutoff = cutoff - timedelta(days=1)
    after_cutoff = cutoff + timedelta(days=1)
    before_event = _event(
        label="usage-before",
        created_at_ms=_local_noon_ms(before_cutoff),
    )
    cutoff_event = _event(
        label="usage-cutoff",
        created_at_ms=_local_noon_ms(cutoff),
    )
    after_event = _event(
        label="usage-after",
        created_at_ms=_local_noon_ms(after_cutoff),
    )
    today_event = _event(
        label="usage-today",
        created_at_ms=_local_noon_ms(today),
    )
    repository = UsageRepository(database_path)
    service = UsageAggregationService(repository=repository, clock=lambda: fixed_now)

    for event in (before_event, cutoff_event, after_event, cutoff_event, today_event):
        await service.consume_audit_event(event)

    assert (
        await repository.list_daily_aggregates(
            local_date=before_cutoff,
            timezone=USAGE_TIMEZONE,
        )
        == ()
    )
    assert await repository.list_daily_aggregates(
        local_date=cutoff,
        timezone=USAGE_TIMEZONE,
    ) == (_aggregate(cutoff),)
    assert await repository.list_daily_aggregates(
        local_date=after_cutoff,
        timezone=USAGE_TIMEZONE,
    ) == (_aggregate(after_cutoff),)
    assert _seen_event_dates(database_path) == (
        cutoff.isoformat(),
        after_cutoff.isoformat(),
        today.isoformat(),
    )
    assert _usage_columns(database_path, "usage_seen_events") == (
        "event_key",
        "local_date",
    )
    assert _usage_columns(database_path, "usage_daily_aggregates") == (
        "local_date",
        "timezone",
        "flow",
        "provider_category",
        "call_count",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "complete",
    )

    reopened_repository = UsageRepository(database_path)
    reopened_service = UsageAggregationService(
        repository=reopened_repository,
        clock=lambda: fixed_now,
    )
    await reopened_service.consume_audit_event(cutoff_event)

    assert await reopened_repository.list_daily_aggregates(
        local_date=cutoff,
        timezone=USAGE_TIMEZONE,
    ) == (_aggregate(cutoff),)
    assert await reopened_repository.list_daily_aggregates(
        local_date=after_cutoff,
        timezone=USAGE_TIMEZONE,
    ) == (_aggregate(after_cutoff),)
    expected_today = UsageSnapshot(
        date=today,
        timezone=USAGE_TIMEZONE,
        call_count=1,
        input_tokens=7,
        output_tokens=2,
        estimated_total_tokens=10,
        complete=True,
    )
    assert await reopened_service.get_today() == expected_today
    assert _seen_event_dates(database_path) == (
        cutoff.isoformat(),
        after_cutoff.isoformat(),
        today.isoformat(),
    )

    app = FastAPI()
    app.include_router(
        create_outfit_admin_usage_router(
            usage_service=reopened_service,
            authentication_dependency=_require_test_bearer,
        )
    )
    with TestClient(app) as client:
        assert client.get("/api/outfit/admin/usage/today").status_code == 401
        response = client.get(
            "/api/outfit/admin/usage/today",
            headers={"Authorization": "Bearer test-token"},
        )

    reopened_snapshot = await reopened_service.get_today()
    assert response.status_code == 200
    assert response.json() == expected_today.model_dump(mode="json")
    assert response.json() == reopened_snapshot.model_dump(mode="json")
    assert response.headers["cache-control"] == "private, no-store"
