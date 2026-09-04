# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Short-lived SQLite persistence for bounded host weather cache facts."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import ValidationError

from miloco.weather.contracts import (
    HostWeatherObservation,
    ResolvedWeatherLocation,
    WeatherLocationQuery,
)


class WeatherRepository:
    """Persist one configured location and one current weather observation."""

    def __init__(self, database_path: str | Path) -> None:
        path = Path(database_path)
        if not path.is_absolute():
            raise ValueError("weather SQLite path must be absolute")
        self._database_path = path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def read_location(
        self,
        query: WeatherLocationQuery,
    ) -> ResolvedWeatherLocation | None:
        """Return the location only when it belongs to the current city query."""

        query = _require_query(query)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    city_name,
                    country_code,
                    latitude,
                    longitude,
                    timezone
                FROM host_weather_location
                WHERE singleton_id = 1
                    AND query_city_name = ?
                    AND query_country_code = ?
                """,
                (query.city_name, query.country_code),
            ).fetchone()
        if row is None:
            return None
        try:
            return ResolvedWeatherLocation.model_validate(dict(row))
        except ValidationError:
            return None

    def write_location(
        self,
        query: WeatherLocationQuery,
        location: ResolvedWeatherLocation,
    ) -> None:
        """Atomically replace the single location after query consistency checks."""

        query = _require_query(query)
        location = _require_location(location)
        if (
            query.city_name != location.city_name
            or query.country_code != location.country_code
        ):
            raise ValueError("weather location query does not match resolved location")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous_query = connection.execute(
                """
                SELECT query_city_name, query_country_code
                FROM host_weather_location
                WHERE singleton_id = 1
                """
            ).fetchone()
            if previous_query is not None and (
                previous_query["query_city_name"] != query.city_name
                or previous_query["query_country_code"] != query.country_code
            ):
                connection.execute(
                    "DELETE FROM host_weather_observation WHERE singleton_id = 1"
                )
            connection.execute(
                """
                INSERT INTO host_weather_location (
                    singleton_id,
                    query_city_name,
                    query_country_code,
                    city_name,
                    country_code,
                    latitude,
                    longitude,
                    timezone
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    query_city_name = excluded.query_city_name,
                    query_country_code = excluded.query_country_code,
                    city_name = excluded.city_name,
                    country_code = excluded.country_code,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    timezone = excluded.timezone
                """,
                (
                    query.city_name,
                    query.country_code,
                    location.city_name,
                    location.country_code,
                    location.latitude,
                    location.longitude,
                    location.timezone,
                ),
            )

    def read_observation(self) -> HostWeatherObservation | None:
        """Return the current bounded observation or None for malformed cache data."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT condition, observed_at_ms, valid_until_ms
                FROM host_weather_observation
                WHERE singleton_id = 1
                """
            ).fetchone()
        if row is None:
            return None
        try:
            return HostWeatherObservation.model_validate(dict(row))
        except ValidationError:
            return None

    def write_observation(self, observation: HostWeatherObservation) -> None:
        """Atomically replace the single already-validated weather observation."""

        observation = _require_observation(observation)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO host_weather_observation (
                    singleton_id,
                    condition,
                    observed_at_ms,
                    valid_until_ms
                ) VALUES (1, ?, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    condition = excluded.condition,
                    observed_at_ms = excluded.observed_at_ms,
                    valid_until_ms = excluded.valid_until_ms
                """,
                (
                    observation.condition,
                    observation.observed_at_ms,
                    observation.valid_until_ms,
                ),
            )

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
                CREATE TABLE IF NOT EXISTS host_weather_location (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    query_city_name TEXT NOT NULL,
                    query_country_code TEXT NOT NULL,
                    city_name TEXT NOT NULL,
                    country_code TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    timezone TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS host_weather_observation (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    condition TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    valid_until_ms INTEGER NOT NULL
                );
                """
            )


def _require_query(query: object) -> WeatherLocationQuery:
    if not isinstance(query, WeatherLocationQuery):
        raise ValueError("weather location query must be validated")
    return query


def _require_location(location: object) -> ResolvedWeatherLocation:
    if not isinstance(location, ResolvedWeatherLocation):
        raise ValueError("weather location must be validated")
    return location


def _require_observation(observation: object) -> HostWeatherObservation:
    if not isinstance(observation, HostWeatherObservation):
        raise ValueError("weather observation must be validated")
    return observation
