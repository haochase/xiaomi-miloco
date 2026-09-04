# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Pure host weather contracts without provider, storage, or Outfit imports."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from miloco.weather.contracts import (
    HostWeatherObservation,
    ResolvedWeatherLocation,
    WeatherCachePort,
    WeatherCondition,
    WeatherLocationQuery,
    WeatherProviderPort,
)
from pydantic import ValidationError


def _query() -> WeatherLocationQuery:
    return WeatherLocationQuery(city_name="北京市", country_code="CN")


def _location() -> ResolvedWeatherLocation:
    return ResolvedWeatherLocation(
        city_name="北京市",
        country_code="CN",
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


def test_location_query_normalizes_city_and_country_and_forbids_extra() -> None:
    query = WeatherLocationQuery(city_name="  北京市  ", country_code=" cn ")

    assert query == _query()
    with pytest.raises(ValidationError):
        WeatherLocationQuery.model_validate(
            {
                **query.model_dump(),
                "provider_url": "https://private.invalid/weather",
            }
        )


@pytest.mark.parametrize(
    "values",
    [
        {"city_name": "", "country_code": "CN"},
        {"city_name": "北京市", "country_code": "C"},
        {"city_name": "北京市", "country_code": "中国"},
    ],
)
def test_location_query_rejects_invalid_identity(values: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        WeatherLocationQuery.model_validate(values)


def test_resolved_location_is_frozen_and_forbids_provider_details() -> None:
    location = _location()

    with pytest.raises(ValidationError):
        ResolvedWeatherLocation.model_validate(
            {
                **location.model_dump(),
                "provider_response": "private response",
            }
        )
    with pytest.raises(ValidationError):
        location.latitude = 0.0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", -90.0001),
        ("latitude", 90.0001),
        ("latitude", True),
        ("latitude", "39.9"),
        ("latitude", float("inf")),
        ("longitude", -180.0001),
        ("longitude", 180.0001),
        ("longitude", True),
        ("longitude", "116.4"),
        ("longitude", float("nan")),
        ("timezone", "Beijing/Local"),
        ("timezone", ""),
    ],
)
def test_resolved_location_rejects_invalid_coordinates_and_timezone(
    field: str,
    value: object,
) -> None:
    values = _location().model_dump()
    values[field] = value

    with pytest.raises(ValidationError):
        ResolvedWeatherLocation.model_validate(values)


@pytest.mark.parametrize("condition", ["snow", "Rain", "clear ", ""])
def test_observation_accepts_only_canonical_supported_conditions(
    condition: str,
) -> None:
    with pytest.raises(ValidationError):
        HostWeatherObservation.model_validate(
            {
                "condition": condition,
                "observed_at_ms": 1_000,
                "valid_until_ms": 2_000,
            }
        )


@pytest.mark.parametrize("invalid_time", [True, -1, 1.5, float("inf"), "1000"])
def test_observation_rejects_invalid_epoch_milliseconds(
    invalid_time: object,
) -> None:
    with pytest.raises(ValidationError):
        HostWeatherObservation.model_validate(
            {
                "condition": "rain",
                "observed_at_ms": invalid_time,
                "valid_until_ms": 2_000,
            }
        )
    with pytest.raises(ValidationError):
        HostWeatherObservation.model_validate(
            {
                "condition": "rain",
                "observed_at_ms": 1_000,
                "valid_until_ms": invalid_time,
            }
        )


@pytest.mark.parametrize("valid_until_ms", [0, 999, 1_000])
def test_observation_requires_validity_after_observation(
    valid_until_ms: int,
) -> None:
    with pytest.raises(ValidationError):
        HostWeatherObservation(
            condition="rain",
            observed_at_ms=1_000,
            valid_until_ms=valid_until_ms,
        )


def test_observation_is_frozen_and_forbids_sensitive_fields() -> None:
    observation = _observation()

    with pytest.raises(ValidationError):
        HostWeatherObservation.model_validate(
            {
                **observation.model_dump(),
                "city_name": "private city",
                "provider_response": "private response",
            }
        )
    with pytest.raises(ValidationError):
        observation.condition = "clear"  # type: ignore[misc]


@dataclass
class _Provider:
    async def resolve_city(
        self,
        query: WeatherLocationQuery,
    ) -> ResolvedWeatherLocation:
        assert query == _query()
        return _location()

    async def fetch_current_condition(
        self,
        location: ResolvedWeatherLocation,
    ) -> WeatherCondition:
        assert location == _location()
        return "rain"


@dataclass
class _Cache:
    location: ResolvedWeatherLocation | None = None
    observation: HostWeatherObservation | None = None

    def read_location(
        self,
        query: WeatherLocationQuery,
    ) -> ResolvedWeatherLocation | None:
        assert query == _query()
        return self.location

    def write_location(
        self,
        query: WeatherLocationQuery,
        location: ResolvedWeatherLocation,
    ) -> None:
        assert query == _query()
        self.location = location

    def read_observation(self) -> HostWeatherObservation | None:
        return self.observation

    def write_observation(self, observation: HostWeatherObservation) -> None:
        self.observation = observation


def _accept_provider(port: WeatherProviderPort) -> WeatherProviderPort:
    return port


def _accept_cache(port: WeatherCachePort) -> WeatherCachePort:
    return port


def test_ports_accept_structural_provider_and_cache_implementations() -> None:
    provider = _Provider()
    cache = _Cache()

    assert _accept_provider(provider) is provider
    assert _accept_cache(cache) is cache
