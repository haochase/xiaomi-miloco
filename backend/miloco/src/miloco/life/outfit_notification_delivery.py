# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Durable, local idempotency for host-owned Outfit notification delivery."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

from miloco.life.outfit_moment_notification import (
    OutfitMomentNotification,
    OutfitMomentNotificationPort,
)
from miloco.life.outfit_moment_runtime import OutfitMomentRuntime
from miloco.life.outfit_storage import OutfitStorage


class OutfitNotificationReceiptRepo:
    """Persist pending claims and successful notification delivery receipts."""

    def __init__(self, storage: OutfitStorage | str | Path):
        self._storage = (
            storage if isinstance(storage, OutfitStorage) else OutfitStorage(storage)
        )
        self._db_path = self._storage.database_path
        self._init_schema()

    @property
    def db_path(self) -> Path:
        """Expose the configured local receipt location for operational checks."""
        return self._db_path

    def try_claim(self, idempotency_key: str) -> bool:
        """Reserve a key until it either succeeds or releases after a failure."""
        idempotency_key = self._require_nonblank(idempotency_key, "idempotency_key")
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO outfit_notification_delivery (
                        idempotency_key, state, delivered_at_ms
                    ) VALUES (?, 'pending', NULL)
                    """,
                    (idempotency_key,),
                )
                conn.commit()
        except sqlite3.IntegrityError:
            return False
        return True

    def mark_delivered(self, idempotency_key: str, *, delivered_at_ms: int) -> None:
        """Persist success only after the injected port returns successfully."""
        idempotency_key = self._require_nonblank(idempotency_key, "idempotency_key")
        if not isinstance(delivered_at_ms, int) or isinstance(delivered_at_ms, bool):
            raise ValueError("delivered_at_ms must be an integer")
        if delivered_at_ms < 0:
            raise ValueError("delivered_at_ms must be non-negative")
        with self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE outfit_notification_delivery
                SET state = 'delivered', delivered_at_ms = ?
                WHERE idempotency_key = ? AND state = 'pending'
                """,
                (delivered_at_ms, idempotency_key),
            ).rowcount
            conn.commit()
        if updated != 1:
            raise RuntimeError("notification delivery claim is unavailable")

    def release_claim(self, idempotency_key: str) -> None:
        """Remove an unsuccessful pending claim so a later attempt can retry."""
        idempotency_key = self._require_nonblank(idempotency_key, "idempotency_key")
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM outfit_notification_delivery
                WHERE idempotency_key = ? AND state = 'pending'
                """,
                (idempotency_key,),
            )
            conn.commit()

    def is_delivered(self, idempotency_key: str) -> bool:
        """Return whether a successful delivery receipt exists for the key."""
        idempotency_key = self._require_nonblank(idempotency_key, "idempotency_key")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM outfit_notification_delivery
                WHERE idempotency_key = ? AND state = 'delivered'
                """,
                (idempotency_key,),
            ).fetchone()
        return row is not None

    def _connect(self):
        return self._storage.connect()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS outfit_notification_delivery (
                    idempotency_key TEXT PRIMARY KEY,
                    state TEXT NOT NULL CHECK (state IN ('pending', 'delivered')),
                    delivered_at_ms INTEGER
                );
                """
            )
            conn.commit()

    @staticmethod
    def _require_nonblank(value: str, field_name: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"{field_name} must not be blank")
        return value


class OutfitMomentNotificationDelivery:
    """Send once locally through an injected, host-owned notification port."""

    def __init__(
        self,
        receipts: OutfitNotificationReceiptRepo,
        port: OutfitMomentNotificationPort,
        *,
        clock_ms: Callable[[], int],
    ) -> None:
        self._receipts = receipts
        self._port = port
        self._clock_ms = clock_ms

    @property
    def receipt_db_path(self) -> Path:
        return self._receipts.db_path

    async def dispatch(self, message: OutfitMomentNotification) -> bool:
        """Return whether this call completed one new notification delivery."""
        if not self._receipts.try_claim(message.idempotency_key):
            return False
        try:
            await self._port.send_outfit_moment_notification(message)
        except Exception:
            self._receipts.release_claim(message.idempotency_key)
            raise
        self._receipts.mark_delivered(
            message.idempotency_key,
            delivered_at_ms=self._clock_ms(),
        )
        return True


def build_outfit_notification_delivery(
    runtime: OutfitMomentRuntime,
    port: OutfitMomentNotificationPort,
    *,
    clock_ms: Callable[[], int] | None = None,
) -> OutfitMomentNotificationDelivery:
    """Build local durable delivery from the configured Outfit runtime only."""
    return OutfitMomentNotificationDelivery(
        OutfitNotificationReceiptRepo(runtime.storage),
        port,
        clock_ms=clock_ms or _current_time_ms,
    )


def _current_time_ms() -> int:
    return int(time.time() * 1000)
