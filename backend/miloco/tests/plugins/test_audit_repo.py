# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""SQLite persistence and strict retention for bounded host audit events."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from miloco.plugins.audit import HostAuditEvent, VersionedHmacDigestor
from miloco.plugins.audit_repo import AuditRepository


def _event(
    *,
    event_value: str,
    created_at_ms: int,
) -> HostAuditEvent:
    digestor = VersionedHmacDigestor(key=b"k" * 32, key_version="audit-v1")
    return HostAuditEvent(
        request_event_digest=digestor.digest_request(event_value),
        device_digest=digestor.digest_device("0123456789abcdef"),
        flow="visual",
        stage="completed",
        status="completed",
        error_code=None,
        elapsed_ms=9,
        frame_count=1,
        provider_call_count=1,
        input_tokens=0,
        output_tokens=0,
        video_tokens=0,
        total_tokens=0,
        usage_complete=True,
        created_at_ms=created_at_ms,
    )


def test_repository_requires_configured_absolute_sqlite_path() -> None:
    with pytest.raises(ValueError, match="absolute"):
        AuditRepository(Path("relative-audit.sqlite"))


def test_repository_creates_missing_absolute_parent_directories(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "audit" / "events.sqlite"

    AuditRepository(database_path)

    assert database_path.parent.is_dir()
    assert database_path.is_file()


@pytest.mark.asyncio
async def test_repository_uses_explicit_columns_and_never_stores_pre_digests(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "audit.sqlite"
    repository = AuditRepository(database_path)
    event = _event(event_value="fedcba9876543210", created_at_ms=10)

    await repository.insert(event)

    with sqlite3.connect(database_path) as connection:
        columns = tuple(
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(host_audit_events)"
            ).fetchall()
        )
        indexes = tuple(
            row[1]
            for row in connection.execute(
                "PRAGMA index_list(host_audit_events)"
            ).fetchall()
        )
        stored_values = connection.execute("SELECT * FROM host_audit_events").fetchone()
        schema_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'host_audit_events'"
        ).fetchone()[0]

    assert columns == (
        "audit_id",
        "request_event_key_version",
        "request_event_digest",
        "device_key_version",
        "device_digest",
        "flow",
        "stage",
        "status",
        "error_code",
        "elapsed_ms",
        "frame_count",
        "provider_call_count",
        "input_tokens",
        "output_tokens",
        "video_tokens",
        "total_tokens",
        "usage_complete",
        "created_at_ms",
    )
    assert "host_audit_events_created_at_idx" in indexes
    assert "JSON" not in schema_sql.upper()
    assert "payload" not in schema_sql.lower()
    assert "fedcba9876543210" not in "|".join(map(str, stored_values))
    assert "0123456789abcdef" not in "|".join(map(str, stored_values))


@pytest.mark.asyncio
async def test_repository_reopens_persisted_typed_rows_in_stable_order(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "audit.sqlite"
    first = _event(event_value="first", created_at_ms=20)
    second = _event(event_value="second", created_at_ms=20)
    repository = AuditRepository(database_path)
    await repository.insert(first)
    await repository.insert(second)

    reopened = AuditRepository(database_path)
    rows = await reopened.list_events()

    assert rows == (first, second)
    assert all(isinstance(row, HostAuditEvent) for row in rows)


@pytest.mark.asyncio
async def test_repository_reopens_rows_in_a_real_python_subprocess(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "subprocess" / "audit.sqlite"
    repository = AuditRepository(database_path)
    event = _event(event_value="subprocess-event", created_at_ms=30)
    await repository.insert(event)
    script = """
import asyncio
import sys
from pathlib import Path

from miloco.plugins.audit_repo import AuditRepository

rows = asyncio.run(AuditRepository(Path(sys.argv[1])).list_events())
print(rows[0].model_dump_json())
"""

    completed = subprocess.run(
        [sys.executable, "-c", script, str(database_path)],
        capture_output=True,
        check=False,
        env=os.environ.copy(),
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert HostAuditEvent.model_validate_json(completed.stdout) == event


@pytest.mark.asyncio
async def test_concurrent_insert_read_and_purge_operations_are_bounded(
    tmp_path: Path,
) -> None:
    repository = AuditRepository(tmp_path / "concurrent" / "audit.sqlite")
    events = tuple(
        _event(event_value=f"event-{index}", created_at_ms=100 + index)
        for index in range(12)
    )
    operations = (
        *(repository.insert(event) for event in events),
        *(repository.list_events() for _ in range(4)),
        *(repository.purge_older_than(cutoff_ms=0) for _ in range(4)),
    )

    await asyncio.wait_for(asyncio.gather(*operations), timeout=5)

    assert await repository.list_events() == events


@pytest.mark.asyncio
async def test_retention_deletes_only_rows_strictly_before_epoch_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "audit.sqlite"
    repository = AuditRepository(database_path)
    cutoff_ms = 1_700_000_000_000
    before = _event(event_value="before", created_at_ms=cutoff_ms - 1)
    at_cutoff = _event(event_value="cutoff", created_at_ms=cutoff_ms)
    after = _event(event_value="after", created_at_ms=cutoff_ms + 1)
    monkeypatch.setenv("TZ", "Pacific/Honolulu")
    await repository.insert(after)
    await repository.insert(before)
    await repository.insert(at_cutoff)

    monkeypatch.setenv("TZ", "Asia/Shanghai")
    deleted = await repository.purge_older_than(cutoff_ms=cutoff_ms)

    assert deleted == 1
    assert await repository.list_events() == (at_cutoff, after)
