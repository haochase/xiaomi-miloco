# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Narrow adaptation from host weather cache to Outfit weather facts."""

from __future__ import annotations

from pydantic import ValidationError

from miloco.outfit.weather_contracts import CachedWeatherObservation
from miloco.weather.contracts import (
    HostWeatherObservation,
    ResolvedWeatherLocation,
    WeatherCachePort,
    WeatherLocationQuery,
)


class OutfitHostWeatherCacheAdapter:
    """Expose only current-query weather facts to the Outfit resolver."""

    __slots__ = ("_cache", "_query")

    def __init__(
        self,
        *,
        cache: WeatherCachePort,
        query: WeatherLocationQuery,
    ) -> None:
        self._cache = cache
        self._query = query

    def read_cached_observation(self) -> CachedWeatherObservation | None:
        """Read each host cache fact once and fail closed on any mismatch."""

        try:
            location = self._cache.read_location(self._query)
        except Exception:
            return None
        if not isinstance(location, ResolvedWeatherLocation) or not (
            location.city_name == self._query.city_name
            and location.country_code == self._query.country_code
        ):
            return None

        try:
            observation = self._cache.read_observation()
        except Exception:
            return None
        if not isinstance(observation, HostWeatherObservation):
            return None
        try:
            return CachedWeatherObservation(
                condition=observation.condition,
                observed_at_ms=observation.observed_at_ms,
                valid_until_ms=observation.valid_until_ms,
            )
        except ValidationError:
            return None
