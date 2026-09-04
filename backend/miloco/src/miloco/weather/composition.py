# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Lazy host composition for the optional city weather runtime."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, TypeAlias

from miloco.config.settings import WeatherSettings
from miloco.weather.contracts import WeatherCachePort

WeatherCompositionErrorCode: TypeAlias = Literal["start_failed", "stop_failed"]


class WeatherRuntimePort(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class WeatherTransportClosePort(Protocol):
    async def aclose(self) -> None: ...


class WeatherCompositionError(RuntimeError):
    """Finite lifecycle failure without component or provider details."""

    def __init__(self, code: WeatherCompositionErrorCode) -> None:
        self.code = code
        super().__init__("host weather lifecycle failed")


@dataclass(frozen=True, slots=True)
class HostWeatherComposition:
    """Own the runtime, readable cache, and transport close lifecycle."""

    runtime: WeatherRuntimePort
    cache: WeatherCachePort
    transport: WeatherTransportClosePort

    async def start(self) -> None:
        try:
            await self.runtime.start()
        except Exception:
            raise WeatherCompositionError("start_failed") from None

    async def stop(self) -> None:
        runtime_failure: BaseException | None = None
        transport_failure: BaseException | None = None
        try:
            await self.runtime.stop()
        except BaseException as error:
            runtime_failure = error
        try:
            await self.transport.aclose()
        except BaseException as error:
            transport_failure = error
        if runtime_failure is not None and not isinstance(runtime_failure, Exception):
            raise runtime_failure
        if transport_failure is not None and not isinstance(
            transport_failure, Exception
        ):
            raise transport_failure
        if runtime_failure is not None or transport_failure is not None:
            raise WeatherCompositionError("stop_failed")


def build_host_weather_runtime(
    settings: WeatherSettings,
    workspace_dir: str | Path,
) -> HostWeatherComposition | None:
    """Build lazily so disabled weather creates no client, path, or task."""

    if not settings.enabled:
        return None
    workspace = Path(workspace_dir)
    if not workspace.is_absolute():
        raise ValueError("weather workspace must be absolute")

    from miloco.weather.http_transport import HttpxWeatherTransport
    from miloco.weather.open_meteo import OpenMeteoWeatherProvider
    from miloco.weather.repository import WeatherRepository
    from miloco.weather.runtime import HostWeatherRuntime
    from miloco.weather.service import WeatherRefreshService

    cache = WeatherRepository(workspace / "weather" / "weather.db")
    transport = HttpxWeatherTransport()
    provider = OpenMeteoWeatherProvider(transport)
    refresh_service = WeatherRefreshService(
        settings,
        provider=provider,
        cache=cache,
        clock_ms=lambda: time.time_ns() // 1_000_000,
    )
    runtime = HostWeatherRuntime(
        refresh_service,
        interval_seconds=settings.refresh_interval_seconds,
    )
    return HostWeatherComposition(
        runtime=runtime,
        cache=cache,
        transport=transport,
    )
