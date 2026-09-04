# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Cancelable lifecycle for periodic host weather refresh."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

_LOGGER = logging.getLogger(__name__)


class WeatherRefreshPort(Protocol):
    """One bounded refresh operation owned by the runtime."""

    async def refresh_once(self) -> object: ...


class HostWeatherRuntime:
    """Run one initial refresh and one cancelable periodic refresh task."""

    def __init__(
        self,
        refresh_service: WeatherRefreshPort,
        *,
        interval_seconds: int,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._refresh_service = refresh_service
        self._interval_seconds = float(_require_interval(interval_seconds))
        self._sleep = sleep
        self._task: asyncio.Task[None] | None = None
        self._start_attempted = False
        self._stopped = False

    async def start(self) -> None:
        """Refresh once before starting exactly one periodic task."""

        if self._start_attempted or self._stopped:
            return
        self._start_attempted = True
        await self._refresh_safely()
        if self._stopped:
            return
        self._task = asyncio.create_task(
            self._run_periodically(),
            name="miloco-host-weather-refresh",
        )

    async def stop(self) -> None:
        """Cancel and await the periodic task once."""

        if self._stopped:
            return
        self._stopped = True
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _run_periodically(self) -> None:
        while True:
            await self._sleep(self._interval_seconds)
            await self._refresh_safely()

    async def _refresh_safely(self) -> None:
        try:
            await self._refresh_service.refresh_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.warning("weather_refresh_failed")


def _require_interval(value: object) -> int:
    if type(value) is not int or not 300 <= value <= 86_400:
        raise ValueError("weather runtime interval must be between 300 and 86400")
    return value
