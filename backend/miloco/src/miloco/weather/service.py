# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""One-shot, rate-limited refresh of host-owned weather cache facts."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from miloco.config.settings import WeatherSettings
from miloco.weather.contracts import (
    HostWeatherObservation,
    ResolvedWeatherLocation,
    WeatherCachePort,
    WeatherLocationQuery,
    WeatherProviderPort,
)

WeatherRefreshStatus: TypeAlias = Literal[
    "disabled",
    "not_due",
    "busy",
    "refreshed",
    "failed",
]
WeatherRefreshCode: TypeAlias = Literal[
    "weather_disabled",
    "refresh_not_due",
    "refresh_busy",
    "refresh_succeeded",
    "clock_failed",
    "cache_read_failed",
    "cache_write_failed",
    "provider_failed",
]
_STATUS_CODES: dict[WeatherRefreshStatus, frozenset[WeatherRefreshCode]] = {
    "disabled": frozenset({"weather_disabled"}),
    "not_due": frozenset({"refresh_not_due"}),
    "busy": frozenset({"refresh_busy"}),
    "refreshed": frozenset({"refresh_succeeded"}),
    "failed": frozenset(
        {
            "clock_failed",
            "cache_read_failed",
            "cache_write_failed",
            "provider_failed",
        }
    ),
}


class WeatherRefreshOutcome(BaseModel):
    """Finite refresh result without location, response, or exception details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: WeatherRefreshStatus
    code: WeatherRefreshCode
    provider_call_count: int = Field(ge=0, le=2, strict=True)
    geocoding_call_count: int = Field(ge=0, le=1, strict=True)

    @model_validator(mode="after")
    def validate_status_and_counts(self) -> Self:
        if self.code not in _STATUS_CODES[self.status]:
            raise ValueError("weather refresh status and code do not match")
        if self.geocoding_call_count > self.provider_call_count:
            raise ValueError("geocoding calls must be included in provider calls")
        if self.provider_call_count - self.geocoding_call_count > 1:
            raise ValueError("weather refresh allows at most one forecast call")
        if self.status in {"disabled", "not_due", "busy"} and (
            self.provider_call_count != 0 or self.geocoding_call_count != 0
        ):
            raise ValueError("non-running refresh outcomes require zero calls")
        if self.status == "refreshed" and (
            self.provider_call_count != self.geocoding_call_count + 1
        ):
            raise ValueError("successful refresh requires one forecast call")
        return self


class WeatherRefreshService:
    """Run one bounded refresh without owning a scheduler or background task."""

    def __init__(
        self,
        settings: WeatherSettings,
        *,
        provider: WeatherProviderPort,
        cache: WeatherCachePort,
        clock_ms: Callable[[], int],
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._cache = cache
        self._clock_ms = clock_ms
        self._query = (
            WeatherLocationQuery(
                city_name=settings.city_name,
                country_code=settings.country_code,
            )
            if settings.enabled and settings.city_name is not None
            else None
        )
        self._refresh_interval_ms = settings.refresh_interval_seconds * 1_000
        self._validity_ms = settings.validity_seconds * 1_000
        self._last_attempt_at_ms: int | None = None
        self._refresh_lock = asyncio.Lock()

    async def refresh_once(self) -> WeatherRefreshOutcome:
        """Run at most one geocode and one forecast call without retry."""

        if not self._settings.enabled:
            return _outcome("disabled", "weather_disabled")
        if self._refresh_lock.locked():
            return _outcome("busy", "refresh_busy")

        async with self._refresh_lock:
            now_ms = self._read_clock()
            if now_ms is None:
                return _outcome("failed", "clock_failed")
            if self._last_attempt_at_ms is not None:
                if now_ms < self._last_attempt_at_ms:
                    return _outcome("failed", "clock_failed")
                if now_ms - self._last_attempt_at_ms < self._refresh_interval_ms:
                    return _outcome("not_due", "refresh_not_due")
            self._last_attempt_at_ms = now_ms

            query = self._query
            if query is None:
                return _outcome("failed", "provider_failed")
            try:
                location = self._cache.read_location(query)
            except Exception:
                return _outcome("failed", "cache_read_failed")
            if location is not None and (
                not isinstance(location, ResolvedWeatherLocation)
                or not _location_matches_query(location, query)
            ):
                return _outcome("failed", "cache_read_failed")

            provider_calls = 0
            geocoding_calls = 0
            if location is None:
                provider_calls = 1
                geocoding_calls = 1
                try:
                    location = await self._provider.resolve_city(query)
                except Exception:
                    return _outcome(
                        "failed",
                        "provider_failed",
                        provider_calls=provider_calls,
                        geocoding_calls=geocoding_calls,
                    )
                if not isinstance(
                    location, ResolvedWeatherLocation
                ) or not _location_matches_query(location, query):
                    return _outcome(
                        "failed",
                        "provider_failed",
                        provider_calls=provider_calls,
                        geocoding_calls=geocoding_calls,
                    )
                try:
                    self._cache.write_location(query, location)
                except Exception:
                    return _outcome(
                        "failed",
                        "cache_write_failed",
                        provider_calls=provider_calls,
                        geocoding_calls=geocoding_calls,
                    )

            provider_calls += 1
            try:
                condition = await self._provider.fetch_current_condition(location)
            except Exception:
                return _outcome(
                    "failed",
                    "provider_failed",
                    provider_calls=provider_calls,
                    geocoding_calls=geocoding_calls,
                )
            try:
                observation = HostWeatherObservation(
                    condition=condition,
                    observed_at_ms=now_ms,
                    valid_until_ms=now_ms + self._validity_ms,
                )
            except ValidationError:
                return _outcome(
                    "failed",
                    "provider_failed",
                    provider_calls=provider_calls,
                    geocoding_calls=geocoding_calls,
                )
            try:
                self._cache.write_observation(observation)
            except Exception:
                return _outcome(
                    "failed",
                    "cache_write_failed",
                    provider_calls=provider_calls,
                    geocoding_calls=geocoding_calls,
                )
            return _outcome(
                "refreshed",
                "refresh_succeeded",
                provider_calls=provider_calls,
                geocoding_calls=geocoding_calls,
            )

    def _read_clock(self) -> int | None:
        try:
            value = self._clock_ms()
        except Exception:
            return None
        if type(value) is not int or value < 0:
            return None
        return value


def _outcome(
    status: WeatherRefreshStatus,
    code: WeatherRefreshCode,
    *,
    provider_calls: int = 0,
    geocoding_calls: int = 0,
) -> WeatherRefreshOutcome:
    return WeatherRefreshOutcome(
        status=status,
        code=code,
        provider_call_count=provider_calls,
        geocoding_call_count=geocoding_calls,
    )


def _location_matches_query(
    location: ResolvedWeatherLocation,
    query: WeatherLocationQuery,
) -> bool:
    return (
        location.city_name == query.city_name
        and location.country_code == query.country_code
    )
