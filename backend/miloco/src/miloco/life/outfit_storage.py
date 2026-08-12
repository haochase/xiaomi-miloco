# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Private SQLite lifecycle management for the Outfit plugin."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

OUTFIT_STORAGE_SCHEMA_VERSION = 1


class OutfitStorageSchemaError(RuntimeError):
    """Raised when a private Outfit database is not compatible with this runtime."""


class OutfitStorage:
    """Own one private Outfit database with short-lived SQLite connections."""

    def __init__(
        self, database_path: str | Path, *, timeout_seconds: float = 10
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._database_path = Path(database_path)
        self._timeout_seconds = timeout_seconds
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    @property
    def database_path(self) -> Path:
        """Return the configured private database location."""
        return self._database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield one configured connection and always close it after the operation."""
        connection = sqlite3.connect(
            str(self._database_path),
            timeout=self._timeout_seconds,
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA synchronous = NORMAL")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize_database(self) -> None:
        connection = sqlite3.connect(
            str(self._database_path),
            timeout=self._timeout_seconds,
        )
        try:
            journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if str(journal_mode).lower() != "wal":
                raise OutfitStorageSchemaError(
                    "Outfit storage must use WAL journal mode"
                )

            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > OUTFIT_STORAGE_SCHEMA_VERSION:
                raise OutfitStorageSchemaError(
                    "Outfit storage schema is newer than this Outfit runtime"
                )
            if version == 0:
                table_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                ).fetchone()[0]
                if table_count:
                    raise OutfitStorageSchemaError(
                        "unversioned Outfit storage requires explicit migration"
                    )
                connection.execute(
                    f"PRAGMA user_version = {OUTFIT_STORAGE_SCHEMA_VERSION}"
                )
            connection.commit()
        finally:
            connection.close()
