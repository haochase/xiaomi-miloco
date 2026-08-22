# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the Xiaomi Miloco License Agreement.

"""Generic FastAPI composition for explicit in-process plugin factories."""

from __future__ import annotations

import logging
from enum import Enum

from fastapi import FastAPI

from miloco.plugins.registry import HostPluginRegistry, PluginFactory

_LOGGER = logging.getLogger(__name__)


class HostCompositionFailureCode(str, Enum):
    """Fixed host-composition failures without exception or route details."""

    REGISTRY_ACTIVATION_FAILED = "plugin_registry_activation_failed"
    ROUTE_MOUNT_FAILED = "plugin_route_mount_failed"
    ROUTE_REMOVAL_FAILED = "plugin_route_removal_failed"
    REGISTRY_SHUTDOWN_FAILED = "plugin_registry_shutdown_failed"


class HostPluginRuntime:
    """Activate one H2 registry and mount its successful route publications."""

    __slots__ = (
        "_registry",
        "_mounted_routes",
        "_failures",
        "_start_attempted",
        "_stop_completed",
    )

    def __init__(self, factories: tuple[PluginFactory, ...]) -> None:
        self._registry = HostPluginRegistry(factories)
        self._mounted_routes: tuple[object, ...] = ()
        self._failures: tuple[HostCompositionFailureCode, ...] = ()
        self._start_attempted = False
        self._stop_completed = False

    @property
    def registry(self) -> HostPluginRegistry:
        return self._registry

    @property
    def failures(self) -> tuple[HostCompositionFailureCode, ...]:
        return self._failures

    async def start(self, app: FastAPI) -> None:
        """Activate and mount once; optional failures never escape core startup."""

        if self._start_attempted or self._stop_completed:
            return
        self._start_attempted = True
        try:
            await self._registry.activate()
        except Exception:
            self._record_failure(HostCompositionFailureCode.REGISTRY_ACTIVATION_FAILED)
            await self._shutdown_registry()
            return

        published_routers = self._registry.routers
        if not published_routers:
            return

        newly_mounted: list[object] = []
        published_routes: tuple[object, ...] = ()
        original_route_ids: set[int] | None = None
        try:
            published_routes = tuple(
                route for router in published_routers for route in router.routes
            )
            if not published_routes:
                return
            original_routes = tuple(app.router.routes)
            original_route_ids = {id(route) for route in original_routes}
            fallback_index = next(
                index
                for index, route in enumerate(original_routes)
                if getattr(route, "name", None) == "spa_handler"
            )
            existing_route_ids = set(original_route_ids)
            for route in published_routes:
                if id(route) in existing_route_ids:
                    continue
                app.router.routes.insert(fallback_index, route)
                newly_mounted.append(route)
                existing_route_ids.add(id(route))
                fallback_index += 1
        except Exception:
            self._mounted_routes = tuple(
                route
                for route in published_routes
                if original_route_ids is not None
                and id(route) not in original_route_ids
            )
            self._remove_mounted_routes(app)
            await self._shutdown_registry()
            self._record_failure(HostCompositionFailureCode.ROUTE_MOUNT_FAILED)
            return
        self._mounted_routes = tuple(newly_mounted)

    async def stop(self, app: FastAPI) -> None:
        """Remove mounted identities, then stop H2 contributions once."""

        if self._stop_completed:
            return
        self._stop_completed = True
        self._remove_mounted_routes(app)
        await self._shutdown_registry()

    def _remove_mounted_routes(self, app: FastAPI) -> None:
        mounted_ids = {id(route) for route in self._mounted_routes}
        if not mounted_ids:
            return
        try:
            remaining_routes = [
                route for route in app.router.routes if id(route) not in mounted_ids
            ]
            try:
                app.router.routes[:] = remaining_routes
            except Exception:
                app.router.routes = remaining_routes
        except Exception:
            self._record_failure(HostCompositionFailureCode.ROUTE_REMOVAL_FAILED)
        finally:
            self._mounted_routes = ()

    async def _shutdown_registry(self) -> None:
        try:
            await self._registry.shutdown()
        except Exception:
            self._record_failure(HostCompositionFailureCode.REGISTRY_SHUTDOWN_FAILED)

    def _record_failure(self, code: HostCompositionFailureCode) -> None:
        self._failures += (code,)
        _LOGGER.warning(code.value)
