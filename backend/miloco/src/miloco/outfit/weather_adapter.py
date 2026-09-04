# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Adapt host-cached weather into the recommendation service's narrow port."""

from __future__ import annotations

from collections.abc import Callable

from miloco.outfit.filtering import WeatherRequirement
from miloco.outfit.weather_contracts import (
    CachedWeatherPort,
    WeatherErrorCode,
    WeatherResolution,
    resolve_cached_weather,
)


class WeatherUnavailableError(RuntimeError):
    """A finite failure that does not expose host cache or provider details."""

    def __init__(self, code: WeatherErrorCode) -> None:
        self.code = code
        super().__init__("cached weather is unavailable")


class CachedWeatherRequirementAdapter:
    """Resolve one host clock and one cached observation per request."""

    def __init__(
        self,
        cache_port: CachedWeatherPort,
        *,
        now_ms: Callable[[], int],
    ) -> None:
        self._cache_port = cache_port
        self._now_ms = now_ms

    def current_resolution(self) -> WeatherResolution:
        """Return a finite snapshot without fetching or retrying weather."""

        try:
            return resolve_cached_weather(
                self._cache_port,
                now_ms=self._now_ms(),
            )
        except Exception:
            return WeatherResolution(
                status="unavailable",
                error_code="weather_read_failed",
            )

    def current_requirement(self) -> WeatherRequirement:
        """Return a supported requirement or fail closed with a fixed code."""

        resolution = self.current_resolution()
        if resolution.status == "unavailable":
            assert resolution.error_code is not None
            raise WeatherUnavailableError(resolution.error_code)
        assert resolution.requirement is not None
        return resolution.requirement
