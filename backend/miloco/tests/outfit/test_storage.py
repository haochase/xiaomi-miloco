# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Storage boundary contracts for the Outfit plugin."""

from pathlib import Path

import pytest
from miloco.outfit.storage import OutfitStorage


def test_storage_rejects_relative_database_path():
    with pytest.raises(ValueError, match="absolute"):
        OutfitStorage(Path("runtime/outfit.db"))


def test_storage_creates_parent_directory_and_empty_database_at_configured_path(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "outfit" / "runtime" / "outfit.db"

    storage = OutfitStorage(database_path)

    assert storage.database_path == database_path
    assert database_path.parent.is_dir()
    assert database_path.is_file()

    with storage.connect() as connection:
        tables = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()

    assert tables == []
