# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Connection-lifecycle contracts for the private Outfit SQLite store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from miloco.life.outfit_storage import OutfitStorage, OutfitStorageSchemaError


def test_storage_configures_private_database_and_closes_operation_connections(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "outfit" / "outfit.db"
    storage = OutfitStorage(database_path)

    with storage.connect() as connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample (value) VALUES ('saved')")
        operation_connection = connection
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        operation_connection.execute("SELECT value FROM sample")

    with sqlite3.connect(database_path) as check:
        assert check.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert check.execute("PRAGMA user_version").fetchone()[0] == 1
        assert check.execute("SELECT value FROM sample").fetchone()[0] == "saved"


def test_storage_rejects_unknown_future_schema_version(tmp_path: Path) -> None:
    database_path = tmp_path / "outfit.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA user_version = 2")

    with pytest.raises(
        OutfitStorageSchemaError, match="newer than this Outfit runtime"
    ):
        OutfitStorage(database_path)
