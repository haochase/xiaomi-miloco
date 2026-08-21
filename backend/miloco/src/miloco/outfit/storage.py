# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Private SQLite storage boundary for the Outfit plugin."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class OutfitStorage:
    """Own the configured absolute path for a new private Outfit database."""

    def __init__(self, database_path: str | Path) -> None:
        configured_path = Path(database_path)
        if not configured_path.is_absolute():
            raise ValueError("Outfit storage database_path must be absolute")

        self._database_path = configured_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_empty_database()

    @property
    def database_path(self) -> Path:
        """Return the caller-configured private database location."""

        return self._database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield one short-lived connection for future owner-scoped repositories."""

        connection = sqlite3.connect(self._database_path)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize_empty_database(self) -> None:
        with sqlite3.connect(self._database_path):
            pass
