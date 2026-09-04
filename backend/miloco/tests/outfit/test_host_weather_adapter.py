# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Narrow host-weather to Outfit cached-observation adapter contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import pytest
from miloco.outfit.host_weather_adapter import OutfitHostWeatherCacheAdapter
from miloco.outfit.weather_contracts import CachedWeatherObservation, CachedWeatherPort
from miloco.weather.contracts import (
    HostWeatherObservation,
    ResolvedWeatherLocation,
    WeatherCachePort,
    WeatherLocationQuery,
)


def _query() -> WeatherLocationQuery:
    return WeatherLocationQuery(city_name="北京市", country_code="CN")


def _location(
    *,
    city_name: str = "北京市",
    country_code: str = "CN",
) -> ResolvedWeatherLocation:
    return ResolvedWeatherLocation(
        city_name=city_name,
        country_code=country_code,
        latitude=39.9042,
        longitude=116.4074,
        timezone="Asia/Shanghai",
    )


def _observation() -> HostWeatherObservation:
    return HostWeatherObservation(
        condition="rain",
        observed_at_ms=1_000,
        valid_until_ms=2_000,
    )


@dataclass
class _Cache:
    location: object = field(default_factory=_location)
    observation: object = field(default_factory=_observation)
    location_error: Exception | None = None
    observation_error: Exception | None = None
    location_reads: list[WeatherLocationQuery] = field(default_factory=list)
    observation_reads: int = 0
    location_writes: int = 0
    observation_writes: int = 0

    def read_location(
        self,
        query: WeatherLocationQuery,
    ) -> ResolvedWeatherLocation | None:
        self.location_reads.append(query)
        if self.location_error is not None:
            raise self.location_error
        return cast(ResolvedWeatherLocation | None, self.location)

    def write_location(
        self,
        query: WeatherLocationQuery,
        location: ResolvedWeatherLocation,
    ) -> None:
        del query, location
        self.location_writes += 1

    def read_observation(self) -> HostWeatherObservation | None:
        self.observation_reads += 1
        if self.observation_error is not None:
            raise self.observation_error
        return cast(HostWeatherObservation | None, self.observation)

    def write_observation(self, observation: HostWeatherObservation) -> None:
        del observation
        self.observation_writes += 1


def _accept_outfit_cache(port: CachedWeatherPort) -> CachedWeatherPort:
    return port


def _adapter(cache: WeatherCachePort) -> OutfitHostWeatherCacheAdapter:
    return OutfitHostWeatherCacheAdapter(cache=cache, query=_query())


def test_matching_location_copies_only_bounded_observation_once() -> None:
    cache = _Cache()
    adapter = _adapter(cache)

    result = _accept_outfit_cache(adapter).read_cached_observation()

    assert result == CachedWeatherObservation(
        condition="rain",
        observed_at_ms=1_000,
        valid_until_ms=2_000,
    )
    assert result is not None
    assert result.model_dump() == {
        "condition": "rain",
        "observed_at_ms": 1_000,
        "valid_until_ms": 2_000,
    }
    assert cache.location_reads == [_query()]
    assert cache.observation_reads == 1
    assert cache.location_writes == 0
    assert cache.observation_writes == 0
    assert "北京市" not in repr(result)
    assert "39.9042" not in repr(result)
    assert "北京市" not in repr(adapter)


@pytest.mark.parametrize(
    "location",
    [
        None,
        {"city_name": "北京市"},
        _location(city_name="上海市"),
        _location(country_code="US"),
    ],
)
def test_missing_invalid_or_wrong_location_stops_before_observation(
    location: object,
) -> None:
    cache = _Cache(location=location)
    adapter = _adapter(cache)

    result = adapter.read_cached_observation()

    assert result is None
    assert cache.location_reads == [_query()]
    assert cache.observation_reads == 0


def test_location_read_failure_is_hidden_and_stops_before_observation() -> None:
    private_detail = "private weather DB at E:/secret/weather.db"
    cache = _Cache(location_error=RuntimeError(private_detail))
    adapter = _adapter(cache)

    result = adapter.read_cached_observation()

    assert result is None
    assert cache.location_reads == [_query()]
    assert cache.observation_reads == 0
    assert private_detail not in repr(adapter)


@pytest.mark.parametrize("observation", [None, {"condition": "rain"}])
def test_missing_or_invalid_observation_fails_closed(observation: object) -> None:
    cache = _Cache(observation=observation)
    adapter = _adapter(cache)

    result = adapter.read_cached_observation()

    assert result is None
    assert cache.location_reads == [_query()]
    assert cache.observation_reads == 1


def test_observation_read_failure_is_hidden_without_retry() -> None:
    private_detail = "private provider response"
    cache = _Cache(observation_error=RuntimeError(private_detail))
    adapter = _adapter(cache)

    result = adapter.read_cached_observation()

    assert result is None
    assert cache.location_reads == [_query()]
    assert cache.observation_reads == 1
    assert private_detail not in repr(adapter)
