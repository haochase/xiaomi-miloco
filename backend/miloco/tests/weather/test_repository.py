# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Host-owned SQLite weather cache repository contracts."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from miloco.weather.contracts import (
    HostWeatherObservation,
    ResolvedWeatherLocation,
    WeatherCachePort,
    WeatherLocationQuery,
)
from miloco.weather.repository import WeatherRepository


def _query(
    *,
    city_name: str = "北京市",
    country_code: str = "CN",
) -> WeatherLocationQuery:
    return WeatherLocationQuery(city_name=city_name, country_code=country_code)


def _location(
    *,
    city_name: str = "北京市",
    country_code: str = "CN",
    latitude: float = 39.9042,
    longitude: float = 116.4074,
) -> ResolvedWeatherLocation:
    return ResolvedWeatherLocation(
        city_name=city_name,
        country_code=country_code,
        latitude=latitude,
        longitude=longitude,
        timezone="Asia/Shanghai",
    )


def _observation(
    *,
    condition: str = "rain",
    observed_at_ms: int = 1_000,
    valid_until_ms: int = 2_000,
) -> HostWeatherObservation:
    return HostWeatherObservation.model_validate(
        {
            "condition": condition,
            "observed_at_ms": observed_at_ms,
            "valid_until_ms": valid_until_ms,
        }
    )


def _accept_cache(port: WeatherCachePort) -> WeatherCachePort:
    return port


def test_relative_path_is_rejected_before_filesystem_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    relative_path = Path("private-weather") / "weather.db"

    with pytest.raises(ValueError, match="absolute"):
        WeatherRepository(relative_path)

    assert not relative_path.parent.exists()


def test_new_repository_creates_parent_and_empty_cache(tmp_path: Path) -> None:
    database_path = tmp_path / "host-weather" / "weather.db"

    repository = WeatherRepository(database_path)

    assert database_path.is_file()
    assert repository.read_location(_query()) is None
    assert repository.read_observation() is None
    assert _accept_cache(repository) is repository


def test_location_round_trip_is_scoped_to_normalized_query(tmp_path: Path) -> None:
    repository = WeatherRepository(tmp_path / "weather.db")
    query = _query()
    location = _location()

    repository.write_location(query, location)

    assert repository.read_location(_query(city_name="  北京市  ")) == location
    assert repository.read_location(_query(city_name="上海市")) is None


def test_location_replace_keeps_exactly_one_current_row(tmp_path: Path) -> None:
    database_path = tmp_path / "weather.db"
    repository = WeatherRepository(database_path)
    repository.write_location(_query(), _location())
    replacement = _location(latitude=39.91, longitude=116.42)

    repository.write_location(_query(), replacement)

    assert repository.read_location(_query()) == replacement
    with sqlite3.connect(database_path) as connection:
        row_count = connection.execute(
            "SELECT COUNT(*) FROM host_weather_location"
        ).fetchone()[0]
    assert row_count == 1


def test_changing_configured_city_atomically_invalidates_old_observation(
    tmp_path: Path,
) -> None:
    repository = WeatherRepository(tmp_path / "weather.db")
    repository.write_location(_query(), _location())
    repository.write_observation(_observation())
    shanghai_query = _query(city_name="上海市")
    shanghai_location = _location(
        city_name="上海市",
        latitude=31.2304,
        longitude=121.4737,
    )

    repository.write_location(shanghai_query, shanghai_location)

    assert repository.read_location(_query()) is None
    assert repository.read_location(shanghai_query) == shanghai_location
    assert repository.read_observation() is None


@pytest.mark.parametrize(
    ("query", "location"),
    [
        (_query(city_name="上海市"), _location()),
        (_query(country_code="US"), _location()),
    ],
)
def test_location_write_rejects_query_mismatch_without_replacing_cache(
    tmp_path: Path,
    query: WeatherLocationQuery,
    location: ResolvedWeatherLocation,
) -> None:
    repository = WeatherRepository(tmp_path / "weather.db")
    original = _location(latitude=39.91)
    repository.write_location(_query(), original)

    with pytest.raises(ValueError, match="location query"):
        repository.write_location(query, location)

    assert repository.read_location(_query()) == original


def test_observation_round_trip_and_replace_are_single_row(tmp_path: Path) -> None:
    database_path = tmp_path / "weather.db"
    repository = WeatherRepository(database_path)
    repository.write_observation(_observation())
    replacement = _observation(
        condition="clear",
        observed_at_ms=2_000,
        valid_until_ms=3_000,
    )

    repository.write_observation(replacement)

    assert repository.read_observation() == replacement
    with sqlite3.connect(database_path) as connection:
        row_count = connection.execute(
            "SELECT COUNT(*) FROM host_weather_observation"
        ).fetchone()[0]
    assert row_count == 1


def test_malformed_location_row_fails_closed(tmp_path: Path) -> None:
    database_path = tmp_path / "weather.db"
    repository = WeatherRepository(database_path)
    repository.write_location(_query(), _location())
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE host_weather_location SET latitude = ? WHERE singleton_id = 1",
            ("private-invalid-coordinate",),
        )

    assert repository.read_location(_query()) is None


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("condition", "snow"),
        ("observed_at_ms", -1),
        ("valid_until_ms", "private-invalid-time"),
    ],
)
def test_malformed_observation_row_fails_closed(
    tmp_path: Path,
    column: str,
    value: object,
) -> None:
    database_path = tmp_path / "weather.db"
    repository = WeatherRepository(database_path)
    repository.write_observation(_observation())
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"UPDATE host_weather_observation SET {column} = ? WHERE singleton_id = 1",
            (value,),
        )

    assert repository.read_observation() is None


def test_schema_contains_only_bounded_weather_cache_columns(tmp_path: Path) -> None:
    database_path = tmp_path / "weather.db"
    WeatherRepository(database_path)

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        location_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(host_weather_location)")
        }
        observation_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(host_weather_observation)")
        }

    assert tables == {"host_weather_location", "host_weather_observation"}
    assert location_columns == {
        "singleton_id",
        "query_city_name",
        "query_country_code",
        "city_name",
        "country_code",
        "latitude",
        "longitude",
        "timezone",
    }
    assert observation_columns == {
        "singleton_id",
        "condition",
        "observed_at_ms",
        "valid_until_ms",
    }
    all_columns = location_columns | observation_columns
    assert not all_columns & {
        "owner",
        "api_key",
        "url",
        "request_headers",
        "provider_response",
        "exception",
        "wardrobe",
        "media",
    }


def test_repository_closes_connections_after_operations(tmp_path: Path) -> None:
    database_path = tmp_path / "weather.db"
    moved_path = tmp_path / "moved-weather.db"
    repository = WeatherRepository(database_path)
    repository.write_location(_query(), _location())
    repository.write_observation(_observation())
    assert repository.read_location(_query()) == _location()
    assert repository.read_observation() == _observation()

    database_path.rename(moved_path)

    assert moved_path.is_file()
    assert not database_path.exists()
