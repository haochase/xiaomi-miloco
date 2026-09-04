# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Strict Open-Meteo parsing through an injected fake JSON transport."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from miloco.weather.contracts import (
    ResolvedWeatherLocation,
    WeatherLocationQuery,
    WeatherProviderPort,
)
from miloco.weather.open_meteo import (
    FORECAST_URL,
    GEOCODING_URL,
    OpenMeteoWeatherProvider,
    WeatherProviderError,
)


@dataclass(frozen=True, slots=True)
class _TransportCall:
    url: str
    params: dict[str, str]
    timeout_seconds: float


@dataclass
class _JsonTransport:
    payload: object
    error: Exception | None = None
    calls: list[_TransportCall] = field(default_factory=list)

    async def get_json(
        self,
        *,
        url: str,
        params: dict[str, str],
        timeout_seconds: float,
    ) -> object:
        self.calls.append(
            _TransportCall(
                url=url,
                params=dict(params),
                timeout_seconds=timeout_seconds,
            )
        )
        if self.error is not None:
            raise self.error
        return self.payload


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


def _city_result(
    *,
    name: object = "北京",
    country_code: object = "CN",
    feature_code: object = "PPLC",
    latitude: object = 39.9042,
    longitude: object = 116.4074,
    timezone: object = "Asia/Shanghai",
) -> dict[str, object]:
    return {
        "name": name,
        "country_code": country_code,
        "feature_code": feature_code,
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "population": 21_893_095,
    }


def _accept_weather_provider(port: WeatherProviderPort) -> WeatherProviderPort:
    return port


@pytest.mark.asyncio
async def test_city_resolution_uses_fixed_endpoint_and_exact_bounded_query() -> None:
    transport = _JsonTransport(
        {
            "results": [
                _city_result(name="北京", country_code="US"),
                _city_result(name="北京", feature_code="ADM1"),
                _city_result(),
                _city_result(name="北京市郊区", feature_code="PPL"),
            ],
            "generationtime_ms": 0.2,
        }
    )
    provider = OpenMeteoWeatherProvider(transport, timeout_seconds=5.0)

    resolved = await _accept_weather_provider(provider).resolve_city(_query())

    assert resolved == _location()
    assert transport.calls == [
        _TransportCall(
            url=GEOCODING_URL,
            params={
                "name": "北京市",
                "count": "10",
                "language": "zh",
                "format": "json",
                "countryCode": "CN",
            },
            timeout_seconds=5.0,
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"results": None}, {"results": []}])
async def test_city_resolution_reports_missing_without_retry(payload: object) -> None:
    transport = _JsonTransport(payload)
    provider = OpenMeteoWeatherProvider(transport)

    with pytest.raises(WeatherProviderError) as exc_info:
        await provider.resolve_city(_query())

    assert exc_info.value.code == "city_missing"
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_city_resolution_rejects_multiple_exact_city_candidates() -> None:
    transport = _JsonTransport(
        {"results": [_city_result(), _city_result(name="北京市")]}
    )
    provider = OpenMeteoWeatherProvider(transport)

    with pytest.raises(WeatherProviderError) as exc_info:
        await provider.resolve_city(_query())

    assert exc_info.value.code == "city_ambiguous"
    assert len(transport.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"results": "private-response"},
        {"results": ["private-response"]},
        {"results": [_city_result(country_code=True)]},
        {"results": [_city_result(feature_code=None)]},
        {"results": [_city_result(latitude="39.9042")]},
        {"results": [_city_result(longitude=float("inf"))]},
        {"results": [_city_result(timezone="Beijing/Local")]},
    ],
)
async def test_city_resolution_rejects_malformed_provider_payload(
    payload: object,
) -> None:
    provider = OpenMeteoWeatherProvider(_JsonTransport(payload))

    with pytest.raises(WeatherProviderError) as exc_info:
        await provider.resolve_city(_query())

    assert exc_info.value.code == "provider_invalid"


@pytest.mark.asyncio
async def test_city_resolution_hides_transport_failure_and_does_not_retry() -> None:
    private_detail = "failed at E:/private/weather.json?secret=credential"
    transport = _JsonTransport({}, error=RuntimeError(private_detail))
    provider = OpenMeteoWeatherProvider(transport)

    with pytest.raises(WeatherProviderError) as exc_info:
        await provider.resolve_city(_query())

    assert exc_info.value.code == "provider_failed"
    assert str(exc_info.value) == "weather provider unavailable"
    assert private_detail not in repr(exc_info.value)
    assert len(transport.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("weather_code", "condition"),
    [
        (0, "clear"),
        (3, "clear"),
        (45, "clear"),
        (48, "clear"),
        (51, "rain"),
        (67, "rain"),
        (80, "rain"),
        (82, "rain"),
        (95, "rain"),
        (99, "rain"),
    ],
)
async def test_forecast_maps_supported_wmo_codes_once(
    weather_code: int,
    condition: str,
) -> None:
    transport = _JsonTransport(
        {
            "latitude": 39.9,
            "longitude": 116.4,
            "current": {"weather_code": weather_code},
        }
    )
    provider = OpenMeteoWeatherProvider(transport, timeout_seconds=4.0)

    resolved = await provider.fetch_current_condition(_location())

    assert resolved == condition
    assert transport.calls == [
        _TransportCall(
            url=FORECAST_URL,
            params={
                "latitude": "39.9042",
                "longitude": "116.4074",
                "current": "weather_code",
                "forecast_days": "1",
            },
            timeout_seconds=4.0,
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "weather_code",
    [-1, 4, 50, 68, 71, 77, 85, 86, 94, 100],
)
async def test_forecast_rejects_snow_and_unknown_wmo_codes(
    weather_code: int,
) -> None:
    transport = _JsonTransport({"current": {"weather_code": weather_code}})
    provider = OpenMeteoWeatherProvider(transport)

    with pytest.raises(WeatherProviderError) as exc_info:
        await provider.fetch_current_condition(_location())

    assert exc_info.value.code == "weather_unsupported"
    assert len(transport.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"current": None},
        {"current": []},
        {"current": {}},
        {"current": {"weather_code": True}},
        {"current": {"weather_code": 61.0}},
        {"current": {"weather_code": "61"}},
    ],
)
async def test_forecast_rejects_malformed_provider_payload(payload: object) -> None:
    provider = OpenMeteoWeatherProvider(_JsonTransport(payload))

    with pytest.raises(WeatherProviderError) as exc_info:
        await provider.fetch_current_condition(_location())

    assert exc_info.value.code == "provider_invalid"


@pytest.mark.asyncio
async def test_forecast_hides_transport_failure_and_does_not_retry() -> None:
    private_detail = "forecast failed for private coordinates"
    transport = _JsonTransport({}, error=RuntimeError(private_detail))
    provider = OpenMeteoWeatherProvider(transport)

    with pytest.raises(WeatherProviderError) as exc_info:
        await provider.fetch_current_condition(_location())

    assert exc_info.value.code == "provider_failed"
    assert private_detail not in repr(exc_info.value)
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "timeout_seconds",
    [True, 0, -1, 30.1, float("inf"), "5"],
)
def test_provider_rejects_invalid_timeout(timeout_seconds: Any) -> None:
    with pytest.raises(ValueError, match="timeout"):
        OpenMeteoWeatherProvider(
            _JsonTransport({}),
            timeout_seconds=timeout_seconds,
        )
