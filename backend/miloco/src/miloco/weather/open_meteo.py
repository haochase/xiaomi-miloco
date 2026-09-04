# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Strict Open-Meteo adapter over a host-injected JSON transport."""

from __future__ import annotations

import math
from typing import Literal, Protocol, TypeAlias

from pydantic import ValidationError

from miloco.weather.contracts import (
    ResolvedWeatherLocation,
    WeatherCondition,
    WeatherLocationQuery,
)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WeatherProviderErrorCode: TypeAlias = Literal[
    "city_missing",
    "city_ambiguous",
    "provider_invalid",
    "provider_failed",
    "weather_unsupported",
]
_CITY_FEATURE_CODES = frozenset({"PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLC"})


class WeatherJsonTransport(Protocol):
    """Return decoded JSON without granting the provider general HTTP access."""

    async def get_json(
        self,
        *,
        url: str,
        params: dict[str, str],
        timeout_seconds: float,
    ) -> object: ...


class WeatherProviderError(RuntimeError):
    """Finite provider failure without response, URL, or transport details."""

    def __init__(self, code: WeatherProviderErrorCode) -> None:
        self.code = code
        super().__init__("weather provider unavailable")


class OpenMeteoWeatherProvider:
    """Resolve one city or current condition with exactly one transport call."""

    def __init__(
        self,
        transport: WeatherJsonTransport,
        *,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._transport = transport
        self._timeout_seconds = _require_timeout(timeout_seconds)

    async def resolve_city(
        self,
        query: WeatherLocationQuery,
    ) -> ResolvedWeatherLocation:
        payload = await self._get_json(
            url=GEOCODING_URL,
            params={
                "name": query.city_name,
                "count": "10",
                "language": "zh",
                "format": "json",
                "countryCode": query.country_code,
            },
        )
        return _parse_city(payload, query)

    async def fetch_current_condition(
        self,
        location: ResolvedWeatherLocation,
    ) -> WeatherCondition:
        payload = await self._get_json(
            url=FORECAST_URL,
            params={
                "latitude": _coordinate_param(location.latitude),
                "longitude": _coordinate_param(location.longitude),
                "current": "weather_code",
                "forecast_days": "1",
            },
        )
        return _parse_current_condition(payload)

    async def _get_json(
        self,
        *,
        url: str,
        params: dict[str, str],
    ) -> object:
        try:
            return await self._transport.get_json(
                url=url,
                params=params,
                timeout_seconds=self._timeout_seconds,
            )
        except Exception:
            raise WeatherProviderError("provider_failed") from None


def _parse_city(
    payload: object,
    query: WeatherLocationQuery,
) -> ResolvedWeatherLocation:
    if not isinstance(payload, dict):
        raise WeatherProviderError("provider_invalid")
    results = payload.get("results")
    if results is None:
        raise WeatherProviderError("city_missing")
    if not isinstance(results, list):
        raise WeatherProviderError("provider_invalid")

    matches: list[ResolvedWeatherLocation] = []
    for raw_result in results:
        if not isinstance(raw_result, dict):
            raise WeatherProviderError("provider_invalid")
        name = raw_result.get("name")
        country_code = raw_result.get("country_code")
        feature_code = raw_result.get("feature_code")
        if (
            not isinstance(name, str)
            or not isinstance(country_code, str)
            or not isinstance(feature_code, str)
        ):
            raise WeatherProviderError("provider_invalid")
        if (
            _city_match_key(name) != _city_match_key(query.city_name)
            or country_code.strip().upper() != query.country_code
            or feature_code not in _CITY_FEATURE_CODES
        ):
            continue
        try:
            matches.append(
                ResolvedWeatherLocation.model_validate(
                    {
                        "city_name": query.city_name,
                        "country_code": query.country_code,
                        "latitude": raw_result.get("latitude"),
                        "longitude": raw_result.get("longitude"),
                        "timezone": raw_result.get("timezone"),
                    }
                )
            )
        except ValidationError:
            raise WeatherProviderError("provider_invalid") from None

    if not matches:
        raise WeatherProviderError("city_missing")
    if len(matches) != 1:
        raise WeatherProviderError("city_ambiguous")
    return matches[0]


def _parse_current_condition(payload: object) -> WeatherCondition:
    if not isinstance(payload, dict):
        raise WeatherProviderError("provider_invalid")
    current = payload.get("current")
    if not isinstance(current, dict):
        raise WeatherProviderError("provider_invalid")
    weather_code = current.get("weather_code")
    if type(weather_code) is not int:
        raise WeatherProviderError("provider_invalid")

    if weather_code in {0, 1, 2, 3, 45, 48}:
        return "clear"
    if 51 <= weather_code <= 67 or 80 <= weather_code <= 82 or 95 <= weather_code <= 99:
        return "rain"
    raise WeatherProviderError("weather_unsupported")


def _city_match_key(city_name: str) -> str:
    normalized = city_name.strip().casefold()
    return normalized[:-1] if normalized.endswith("市") else normalized


def _coordinate_param(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _require_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("weather provider timeout must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 < normalized <= 30:
        raise ValueError("weather provider timeout must be within 30 seconds")
    return normalized
