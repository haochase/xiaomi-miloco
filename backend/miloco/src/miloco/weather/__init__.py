# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Host-owned weather contracts and adapters."""

from miloco.weather.contracts import (
    HostWeatherObservation,
    ResolvedWeatherLocation,
    WeatherCachePort,
    WeatherCondition,
    WeatherLocationQuery,
    WeatherProviderPort,
)

__all__ = [
    "HostWeatherObservation",
    "ResolvedWeatherLocation",
    "WeatherCachePort",
    "WeatherCondition",
    "WeatherLocationQuery",
    "WeatherProviderPort",
]
