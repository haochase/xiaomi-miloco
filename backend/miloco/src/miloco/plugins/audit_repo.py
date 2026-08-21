# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Short-lived SQLite persistence for generic host audit events."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from miloco.plugins.audit import HostAuditEvent, VersionedHmacDigest


class AuditRepository:
    """Persist finite audit columns at one explicitly configured absolute path."""

    def __init__(self, database_path: Path) -> None:
        path = Path(database_path)
        if not path.is_absolute():
            raise ValueError("audit SQLite path must be absolute")
        self._database_path = path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    async def insert(self, event: HostAuditEvent) -> None:
        await asyncio.to_thread(self._insert, event)

    async def purge_older_than(self, *, cutoff_ms: int) -> int:
        return await asyncio.to_thread(self._purge_older_than, cutoff_ms)

    async def list_events(self) -> tuple[HostAuditEvent, ...]:
        return await asyncio.to_thread(self._list_events)

    def _insert(self, event: HostAuditEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO host_audit_events (
                    request_event_key_version,
                    request_event_digest,
                    device_key_version,
                    device_digest,
                    flow,
                    stage,
                    status,
                    error_code,
                    elapsed_ms,
                    frame_count,
                    provider_call_count,
                    input_tokens,
                    output_tokens,
                    video_tokens,
                    total_tokens,
                    usage_complete,
                    created_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.request_event_digest.key_version,
                    event.request_event_digest.digest,
                    event.device_digest.key_version,
                    event.device_digest.digest,
                    event.flow,
                    event.stage,
                    event.status,
                    event.error_code,
                    event.elapsed_ms,
                    event.frame_count,
                    event.provider_call_count,
                    event.input_tokens,
                    event.output_tokens,
                    event.video_tokens,
                    event.total_tokens,
                    int(event.usage_complete),
                    event.created_at_ms,
                ),
            )

    def _purge_older_than(self, cutoff_ms: int) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM host_audit_events WHERE created_at_ms < ?",
                (cutoff_ms,),
            )
            return cursor.rowcount

    def _list_events(self) -> tuple[HostAuditEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    request_event_key_version,
                    request_event_digest,
                    device_key_version,
                    device_digest,
                    flow,
                    stage,
                    status,
                    error_code,
                    elapsed_ms,
                    frame_count,
                    provider_call_count,
                    input_tokens,
                    output_tokens,
                    video_tokens,
                    total_tokens,
                    usage_complete,
                    created_at_ms
                FROM host_audit_events
                ORDER BY created_at_ms ASC, audit_id ASC
                """
            ).fetchall()
        return tuple(_event_from_row(row) for row in rows)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._database_path), timeout=1.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS host_audit_events (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_event_key_version TEXT NOT NULL,
                    request_event_digest TEXT NOT NULL,
                    device_key_version TEXT NOT NULL,
                    device_digest TEXT NOT NULL,
                    flow TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_code TEXT,
                    elapsed_ms INTEGER NOT NULL,
                    frame_count INTEGER NOT NULL,
                    provider_call_count INTEGER NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    video_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    usage_complete INTEGER NOT NULL,
                    created_at_ms INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS host_audit_events_created_at_idx
                ON host_audit_events (created_at_ms, audit_id);
                """
            )


def _event_from_row(row: sqlite3.Row) -> HostAuditEvent:
    return HostAuditEvent(
        request_event_digest=VersionedHmacDigest(
            key_version=row["request_event_key_version"],
            digest=row["request_event_digest"],
        ),
        device_digest=VersionedHmacDigest(
            key_version=row["device_key_version"],
            digest=row["device_digest"],
        ),
        flow=row["flow"],
        stage=row["stage"],
        status=row["status"],
        error_code=row["error_code"],
        elapsed_ms=row["elapsed_ms"],
        frame_count=row["frame_count"],
        provider_call_count=row["provider_call_count"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        video_tokens=row["video_tokens"],
        total_tokens=row["total_tokens"],
        usage_complete=bool(row["usage_complete"]),
        created_at_ms=row["created_at_ms"],
    )
