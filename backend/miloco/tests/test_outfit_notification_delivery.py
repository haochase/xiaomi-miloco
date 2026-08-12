# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Durable local delivery contracts for Outfit moment notifications."""

import sqlite3
from pathlib import Path

import pytest
from miloco.life.outfit_installation import OutfitRuntimeContext
from miloco.life.outfit_moment_notification import OutfitMomentNotification
from miloco.life.outfit_moment_runtime import build_outfit_moment_runtime
from miloco.life.outfit_notification_delivery import (
    OutfitNotificationReceiptRepo,
    build_outfit_notification_delivery,
)


class RecordingNotificationPort:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[OutfitMomentNotification] = []

    async def send_outfit_moment_notification(
        self,
        message: OutfitMomentNotification,
    ) -> None:
        if self.fail:
            raise RuntimeError("transport unavailable")
        self.messages.append(message)


def _runtime(tmp_path: Path):
    workspace_dir = tmp_path / "miloco-home"
    workspace_dir.mkdir()
    return build_outfit_moment_runtime(
        OutfitRuntimeContext(
            primary_person_id="primary-person",
            workspace_dir=workspace_dir,
            storage_dir=workspace_dir / "outfit",
        ),
        clock_ms=lambda: 2_000,
    )


def _message() -> OutfitMomentNotification:
    return OutfitMomentNotification(
        summary="A confirmed outfit moment is ready to review.",
        deep_link_path="/#/agents/outfit/moments/moment-1",
        panel_url=None,
        idempotency_key="outfit-moment-v1:test-key",
    )


@pytest.mark.asyncio
async def test_delivery_persists_successful_receipts_across_new_instances(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    message = _message()
    first_port = RecordingNotificationPort()
    first = build_outfit_notification_delivery(
        runtime,
        first_port,
        clock_ms=lambda: 3_000,
    )

    assert await first.dispatch(message) is True
    assert first_port.messages == [message]
    assert first.receipt_db_path == runtime.database_path
    with sqlite3.connect(runtime.database_path) as connection:
        assert connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'outfit_notification_delivery'
            """
        ).fetchone()

    second_port = RecordingNotificationPort()
    second = build_outfit_notification_delivery(
        runtime,
        second_port,
        clock_ms=lambda: 4_000,
    )

    assert await second.dispatch(message) is False
    assert second_port.messages == []


@pytest.mark.asyncio
async def test_failed_delivery_releases_its_claim_for_a_later_retry(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    message = _message()
    receipts = OutfitNotificationReceiptRepo(runtime.storage)
    failing = build_outfit_notification_delivery(
        runtime,
        RecordingNotificationPort(fail=True),
        clock_ms=lambda: 3_000,
    )

    with pytest.raises(RuntimeError, match="transport unavailable"):
        await failing.dispatch(message)
    assert not receipts.is_delivered(message.idempotency_key)

    retry_port = RecordingNotificationPort()
    retry = build_outfit_notification_delivery(
        runtime,
        retry_port,
        clock_ms=lambda: 4_000,
    )

    assert await retry.dispatch(message) is True
    assert retry_port.messages == [message]
    assert receipts.is_delivered(message.idempotency_key)
