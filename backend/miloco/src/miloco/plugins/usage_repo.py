# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the Xiaomi Miloco License Agreement.

"""Atomic short-lived SQLite persistence for sanitized daily usage."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from miloco.plugins.usage import DailyUsageAggregate, SanitizedUsageEvent


class UsageRepository:
    """Persist only irreversible event keys and finite aggregate dimensions."""

    def __init__(self, database_path: Path) -> None:
        path = Path(database_path)
        if not path.is_absolute():
            raise ValueError("usage SQLite path must be absolute")
        self._database_path = path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    async def record_usage_event(self, event: SanitizedUsageEvent) -> bool:
        return await asyncio.to_thread(self._record_usage_event, event)

    async def list_daily_aggregates(
        self,
        *,
        local_date: date,
        timezone: str,
    ) -> tuple[DailyUsageAggregate, ...]:
        return await asyncio.to_thread(
            self._list_daily_aggregates,
            local_date,
            timezone,
        )

    async def purge_before(self, *, cutoff_date: date) -> int:
        return await asyncio.to_thread(self._purge_before, cutoff_date)

    def _record_usage_event(self, event: SanitizedUsageEvent) -> bool:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            inserted = connection.execute(
                """
                INSERT OR IGNORE INTO usage_seen_events (
                    event_key,
                    local_date
                ) VALUES (?, ?)
                """,
                (event.event_key, event.local_date.isoformat()),
            )
            if inserted.rowcount == 0:
                return False

            key = (
                event.local_date.isoformat(),
                event.timezone,
                event.flow,
                event.provider_category,
            )
            aggregate = connection.execute(
                """
                SELECT
                    call_count,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    complete
                FROM usage_daily_aggregates
                WHERE
                    local_date = ?
                    AND timezone = ?
                    AND flow = ?
                    AND provider_category = ?
                """,
                key,
            ).fetchone()
            if aggregate is None:
                connection.execute(
                    """
                    INSERT INTO usage_daily_aggregates (
                        local_date,
                        timezone,
                        flow,
                        provider_category,
                        call_count,
                        input_tokens,
                        output_tokens,
                        total_tokens,
                        complete
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        *key,
                        str(event.call_count),
                        str(event.input_tokens),
                        str(event.output_tokens),
                        str(event.total_tokens),
                        int(event.complete),
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE usage_daily_aggregates
                    SET
                        call_count = ?,
                        input_tokens = ?,
                        output_tokens = ?,
                        total_tokens = ?,
                        complete = ?
                    WHERE
                        local_date = ?
                        AND timezone = ?
                        AND flow = ?
                        AND provider_category = ?
                    """,
                    (
                        str(int(aggregate["call_count"]) + event.call_count),
                        str(int(aggregate["input_tokens"]) + event.input_tokens),
                        str(int(aggregate["output_tokens"]) + event.output_tokens),
                        str(int(aggregate["total_tokens"]) + event.total_tokens),
                        int(bool(aggregate["complete"]) and event.complete),
                        *key,
                    ),
                )
        return True

    def _list_daily_aggregates(
        self,
        local_date: date,
        timezone: str,
    ) -> tuple[DailyUsageAggregate, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    local_date,
                    timezone,
                    flow,
                    provider_category,
                    call_count,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    complete
                FROM usage_daily_aggregates
                WHERE local_date = ? AND timezone = ?
                ORDER BY flow ASC, provider_category ASC
                """,
                (local_date.isoformat(), timezone),
            ).fetchall()
        return tuple(_aggregate_from_row(row) for row in rows)

    def _purge_before(self, cutoff_date: date) -> int:
        cutoff = cutoff_date.isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM usage_seen_events WHERE local_date < ?",
                (cutoff,),
            )
            deleted = connection.execute(
                "DELETE FROM usage_daily_aggregates WHERE local_date < ?",
                (cutoff,),
            )
            return deleted.rowcount

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self._database_path), timeout=5.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS usage_seen_events (
                    event_key TEXT PRIMARY KEY,
                    local_date TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS usage_seen_events_local_date_idx
                ON usage_seen_events (local_date, event_key);

                CREATE TABLE IF NOT EXISTS usage_daily_aggregates (
                    local_date TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    flow TEXT NOT NULL,
                    provider_category TEXT NOT NULL,
                    call_count TEXT NOT NULL,
                    input_tokens TEXT NOT NULL,
                    output_tokens TEXT NOT NULL,
                    total_tokens TEXT NOT NULL,
                    complete INTEGER NOT NULL,
                    PRIMARY KEY (local_date, timezone, flow, provider_category)
                );
                """
            )


def _aggregate_from_row(row: sqlite3.Row) -> DailyUsageAggregate:
    return DailyUsageAggregate(
        local_date=date.fromisoformat(row["local_date"]),
        timezone=row["timezone"],
        flow=row["flow"],
        provider_category=row["provider_category"],
        call_count=int(row["call_count"]),
        input_tokens=int(row["input_tokens"]),
        output_tokens=int(row["output_tokens"]),
        total_tokens=int(row["total_tokens"]),
        complete=bool(row["complete"]),
    )
