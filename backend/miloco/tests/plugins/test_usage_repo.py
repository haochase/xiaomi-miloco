# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the Xiaomi Miloco License Agreement.

"""Atomic, private SQLite persistence contracts for daily usage."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from miloco.plugins.usage import USAGE_TIMEZONE, SanitizedUsageEvent
from miloco.plugins.usage_repo import UsageRepository


def _event(
    event_key: str,
    *,
    local_date: date = date(2026, 4, 2),
    flow: str = "visual",
    provider_category: str = "vision_provider",
    call_count: int = 1,
    input_tokens: int = 8,
    output_tokens: int = 3,
    total_tokens: int = 13,
    complete: bool = True,
) -> SanitizedUsageEvent:
    return SanitizedUsageEvent(
        event_key=event_key,
        local_date=local_date,
        timezone=USAGE_TIMEZONE,
        flow=flow,
        provider_category=provider_category,
        call_count=call_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        complete=complete,
    )


def test_repository_requires_absolute_path_and_creates_nested_schema(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="absolute"):
        UsageRepository(Path("relative/usage.db"))

    database_path = tmp_path / "nested" / "usage" / "usage.db"
    UsageRepository(database_path)

    assert database_path.is_file()
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"usage_seen_events", "usage_daily_aggregates"} <= tables


@pytest.mark.asyncio
async def test_atomic_record_dedupes_reopen_and_ands_completeness(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "usage.db"
    first = UsageRepository(database_path)

    assert await first.record_usage_event(_event("a" * 64)) is True
    assert await first.record_usage_event(_event("a" * 64)) is False

    reopened = UsageRepository(database_path)
    assert (
        await reopened.record_usage_event(
            _event(
                "b" * 64,
                input_tokens=5,
                output_tokens=2,
                total_tokens=7,
                complete=False,
            )
        )
        is True
    )
    rows = await reopened.list_daily_aggregates(
        local_date=date(2026, 4, 2),
        timezone=USAGE_TIMEZONE,
    )

    assert [row.model_dump() for row in rows] == [
        {
            "local_date": date(2026, 4, 2),
            "timezone": USAGE_TIMEZONE,
            "flow": "visual",
            "provider_category": "vision_provider",
            "call_count": 2,
            "input_tokens": 13,
            "output_tokens": 5,
            "total_tokens": 20,
            "complete": False,
        }
    ]


@pytest.mark.asyncio
async def test_concurrent_duplicate_and_unique_writes_count_once(
    tmp_path: Path,
) -> None:
    repository = UsageRepository(tmp_path / "usage.db")
    events = [_event(f"{index:064x}") for index in range(20)]

    results = await asyncio.gather(
        *(repository.record_usage_event(event) for event in events),
        *(repository.record_usage_event(event) for event in events),
    )
    rows = await repository.list_daily_aggregates(
        local_date=date(2026, 4, 2),
        timezone=USAGE_TIMEZONE,
    )

    assert sum(results) == 20
    assert len(rows) == 1
    assert rows[0].call_count == 20
    assert rows[0].total_tokens == 260


@pytest.mark.asyncio
async def test_token_totals_remain_exact_beyond_sqlite_integer_limit(
    tmp_path: Path,
) -> None:
    repository = UsageRepository(tmp_path / "usage.db")
    sqlite_max = (1 << 63) - 1

    await repository.record_usage_event(
        _event(
            "d" * 64,
            input_tokens=sqlite_max,
            output_tokens=0,
            total_tokens=sqlite_max,
        )
    )
    await repository.record_usage_event(
        _event(
            "e" * 64,
            input_tokens=1,
            output_tokens=0,
            total_tokens=1,
        )
    )
    rows = await repository.list_daily_aggregates(
        local_date=date(2026, 4, 2),
        timezone=USAGE_TIMEZONE,
    )

    assert rows[0].input_tokens == 1 << 63
    assert rows[0].total_tokens == 1 << 63
    with sqlite3.connect(tmp_path / "usage.db") as connection:
        stored = connection.execute(
            "SELECT typeof(input_tokens), input_tokens FROM usage_daily_aggregates"
        ).fetchone()
    assert stored == ("text", str(1 << 63))


@pytest.mark.asyncio
async def test_rows_are_stable_and_strict_retention_keeps_exact_cutoff(
    tmp_path: Path,
) -> None:
    repository = UsageRepository(tmp_path / "usage.db")
    await repository.record_usage_event(_event("1" * 64, local_date=date(2026, 1, 1)))
    await repository.record_usage_event(_event("2" * 64, local_date=date(2026, 1, 2)))
    await repository.record_usage_event(
        _event(
            "3" * 64,
            local_date=date(2026, 1, 2),
            flow="voice",
            provider_category="voice_provider",
        )
    )

    deleted = await repository.purge_before(cutoff_date=date(2026, 1, 2))
    rows = await repository.list_daily_aggregates(
        local_date=date(2026, 1, 2),
        timezone=USAGE_TIMEZONE,
    )

    assert deleted == 1
    assert [(row.flow, row.provider_category) for row in rows] == [
        ("visual", "vision_provider"),
        ("voice", "voice_provider"),
    ]
    with sqlite3.connect(tmp_path / "usage.db") as connection:
        seen_dates = connection.execute(
            "SELECT DISTINCT local_date FROM usage_seen_events ORDER BY local_date"
        ).fetchall()
    assert seen_dates == [("2026-01-02",)]


@pytest.mark.asyncio
async def test_subprocess_reopen_persists_aggregate(tmp_path: Path) -> None:
    database_path = (tmp_path / "usage.db").resolve()
    repository = UsageRepository(database_path)
    await repository.record_usage_event(_event("c" * 64))
    script = "\n".join(
        (
            "import asyncio, json, sys",
            "from datetime import date",
            "from pathlib import Path",
            "from miloco.plugins.usage import USAGE_TIMEZONE",
            "from miloco.plugins.usage_repo import UsageRepository",
            "repo = UsageRepository(Path(sys.argv[1]))",
            "rows = asyncio.run(repo.list_daily_aggregates(local_date=date(2026, 4, 2), timezone=USAGE_TIMEZONE))",
            "print(json.dumps([row.model_dump(mode='json') for row in rows], sort_keys=True))",
        )
    )
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    completed = subprocess.run(
        [sys.executable, "-c", script, str(database_path)],
        cwd=Path(__file__).parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(completed.stdout) == [
        {
            "call_count": 1,
            "complete": True,
            "flow": "visual",
            "input_tokens": 8,
            "local_date": "2026-04-02",
            "output_tokens": 3,
            "provider_category": "vision_provider",
            "timezone": USAGE_TIMEZONE,
            "total_tokens": 13,
        }
    ]


def test_schema_never_stores_h4_or_private_fields(tmp_path: Path) -> None:
    database_path = tmp_path / "usage.db"
    UsageRepository(database_path)

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for table in ("usage_seen_events", "usage_daily_aggregates")
            for row in connection.execute(f"PRAGMA table_info({table})")
        }

    prohibited = (
        "request",
        "device",
        "digest",
        "owner",
        "model",
        "error",
        "prompt",
        "raw",
        "hmac",
    )
    assert not any(term in column for term in prohibited for column in columns)
