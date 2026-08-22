# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Generic FastAPI host composition for successful H2 publications."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from miloco.plugins.host_composition import (
    HostCompositionFailureCode,
    HostPluginRuntime,
)
from miloco.plugins.registry import (
    PluginFactory,
    PluginFailureCode,
    PluginLifecycleStage,
)


class _Contribution:
    def __init__(
        self,
        plugin_id: str,
        events: list[str],
        *,
        routers: tuple[APIRouter, ...] = (),
        start_error: bool = False,
        publish_error: bool = False,
        stop_error: bool = False,
    ) -> None:
        self.id = plugin_id
        self._events = events
        self._routers = routers
        self._start_error = start_error
        self._publish_error = publish_error
        self._stop_error = stop_error

    async def start(self) -> None:
        self._events.append(f"start:{self.id}")
        if self._start_error:
            raise RuntimeError("private-start-detail")

    async def stop(self) -> None:
        self._events.append(f"stop:{self.id}")
        if self._stop_error:
            raise RuntimeError("private-stop-detail")

    def routers(self) -> tuple[APIRouter, ...]:
        if self._publish_error:
            raise RuntimeError("private-publish-detail")
        return self._routers

    def panel_capabilities(self) -> tuple[str, ...]:
        return (self.id,)


def _factory(
    plugin_id: str,
    contribution: _Contribution | None,
    events: list[str],
    *,
    build_error: bool = False,
) -> PluginFactory:
    def build():
        events.append(f"build:{plugin_id}")
        if build_error:
            raise RuntimeError("private-build-detail")
        assert contribution is not None
        return contribution

    return PluginFactory(id=plugin_id, build=build)


def _host() -> tuple[FastAPI, APIRoute, APIRoute]:
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/{full_path:path}", name="spa_handler")
    async def spa_handler(full_path: str) -> dict[str, str]:
        return {"path": full_path}

    health_route, spa_route = (
        route for route in app.router.routes if isinstance(route, APIRoute)
    )
    return app, health_route, spa_route


def _router(path: str) -> tuple[APIRouter, APIRoute]:
    router = APIRouter()

    @router.get(path)
    async def endpoint() -> dict[str, bool]:
        return {"ok": True}

    route = router.routes[0]
    assert isinstance(route, APIRoute)
    return router, route


@pytest.mark.asyncio
async def test_empty_runtime_is_an_idempotent_noop_without_spa_fallback() -> None:
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    original_routes = tuple(app.router.routes)
    runtime = HostPluginRuntime(())

    await runtime.start(app)
    await runtime.start(app)
    await runtime.stop(app)
    await runtime.stop(app)

    assert tuple(app.router.routes) == original_routes
    assert runtime.failures == ()


@pytest.mark.asyncio
async def test_success_mounts_exact_routes_once_before_spa_and_removes_on_stop() -> (
    None
):
    events: list[str] = []
    app, health_route, spa_route = _host()
    first_router, first_route = _router("/plugin/first")
    second_router, second_route = _router("/plugin/second")
    contribution = _Contribution(
        "active", events, routers=(first_router, second_router)
    )
    runtime = HostPluginRuntime((_factory("active", contribution, events),))

    await runtime.start(app)
    await runtime.start(app)

    assert events == ["build:active", "start:active"]
    assert app.router.routes.count(first_route) == 1
    assert app.router.routes.count(second_route) == 1
    assert app.router.routes.index(first_route) < app.router.routes.index(second_route)
    assert app.router.routes.index(second_route) < app.router.routes.index(spa_route)
    assert health_route in app.router.routes

    await runtime.stop(app)
    await runtime.stop(app)

    assert events == ["build:active", "start:active", "stop:active"]
    assert first_route not in app.router.routes
    assert second_route not in app.router.routes
    assert health_route in app.router.routes
    assert spa_route in app.router.routes


@pytest.mark.asyncio
async def test_preexisting_identical_route_is_not_duplicated_or_removed() -> None:
    events: list[str] = []
    app, _health_route, spa_route = _host()
    plugin_router, plugin_route = _router("/plugin/preexisting")
    app.router.routes.insert(app.router.routes.index(spa_route), plugin_route)
    contribution = _Contribution("active", events, routers=(plugin_router,))
    runtime = HostPluginRuntime((_factory("active", contribution, events),))

    await runtime.start(app)

    assert app.router.routes.count(plugin_route) == 1

    await runtime.stop(app)

    assert app.router.routes.count(plugin_route) == 1
    assert events == ["build:active", "start:active", "stop:active"]


@pytest.mark.asyncio
async def test_build_start_and_publish_failures_preserve_core_routes() -> None:
    events: list[str] = []
    app, health_route, spa_route = _host()
    active_router, active_route = _router("/plugin/active")
    runtime = HostPluginRuntime(
        (
            _factory("build", None, events, build_error=True),
            _factory("start", _Contribution("start", events, start_error=True), events),
            _factory(
                "publish",
                _Contribution("publish", events, publish_error=True),
                events,
            ),
            _factory(
                "active",
                _Contribution("active", events, routers=(active_router,)),
                events,
            ),
        )
    )

    await runtime.start(app)

    assert health_route in app.router.routes
    assert spa_route in app.router.routes
    assert active_route in app.router.routes
    assert [failure.stage for failure in runtime.registry.failures] == [
        PluginLifecycleStage.BUILD,
        PluginLifecycleStage.START,
        PluginLifecycleStage.PUBLISH,
    ]


class _FailingRouteList(list):
    def __init__(
        self,
        values,
        reject: Callable[[object], bool],
        *,
        mutate_before_failure: bool = False,
    ) -> None:
        super().__init__(values)
        self._reject = reject
        self._mutate_before_failure = mutate_before_failure

    def insert(self, index: int, value: object) -> None:
        if self._reject(value):
            if self._mutate_before_failure:
                super().insert(index, value)
            raise RuntimeError("C:/private/mount-secret")
        super().insert(index, value)


class _ExplodingRouteIterable(list):
    def __iter__(self):
        raise RuntimeError("C:/private/route-enumeration-secret")


@pytest.mark.asyncio
async def test_route_enumeration_failure_isolated_as_fixed_mount_failure(
    caplog,
) -> None:
    events: list[str] = []
    app, health_route, spa_route = _host()
    plugin_router = APIRouter()
    plugin_router.routes = _ExplodingRouteIterable()
    contribution = _Contribution("active", events, routers=(plugin_router,))
    runtime = HostPluginRuntime((_factory("active", contribution, events),))

    await runtime.start(app)

    assert events == ["build:active", "start:active", "stop:active"]
    assert health_route in app.router.routes
    assert spa_route in app.router.routes
    assert runtime.failures == (HostCompositionFailureCode.ROUTE_MOUNT_FAILED,)
    assert "plugin_route_mount_failed" in caplog.text
    assert "route-enumeration-secret" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("mutate_before_failure", (False, True))
async def test_mount_failure_rolls_back_and_shuts_down_without_sensitive_logs(
    caplog,
    mutate_before_failure: bool,
) -> None:
    events: list[str] = []
    app, health_route, spa_route = _host()
    first_router, first_route = _router("/plugin/first")
    second_router, second_route = _router("/plugin/second")
    contribution = _Contribution(
        "active", events, routers=(first_router, second_router)
    )
    runtime = HostPluginRuntime((_factory("active", contribution, events),))
    app.router.routes = _FailingRouteList(
        app.router.routes,
        lambda route: route is second_route,
        mutate_before_failure=mutate_before_failure,
    )

    await runtime.start(app)

    assert first_route not in app.router.routes
    assert second_route not in app.router.routes
    assert health_route in app.router.routes
    assert spa_route in app.router.routes
    assert events == ["build:active", "start:active", "stop:active"]
    assert runtime.failures == (HostCompositionFailureCode.ROUTE_MOUNT_FAILED,)
    assert "plugin_route_mount_failed" in caplog.text
    assert "mount-secret" not in caplog.text


class _SliceFailingRouteList(list):
    def __setitem__(self, key, value) -> None:
        if isinstance(key, slice):
            raise RuntimeError("C:/private/removal-secret")
        super().__setitem__(key, value)


@pytest.mark.asyncio
async def test_stop_falls_back_when_in_place_route_removal_fails(caplog) -> None:
    events: list[str] = []
    app, health_route, spa_route = _host()
    plugin_router, plugin_route = _router("/plugin/active")
    contribution = _Contribution("active", events, routers=(plugin_router,))
    runtime = HostPluginRuntime((_factory("active", contribution, events),))
    await runtime.start(app)
    app.router.routes = _SliceFailingRouteList(app.router.routes)

    await runtime.stop(app)

    assert plugin_route not in app.router.routes
    assert health_route in app.router.routes
    assert spa_route in app.router.routes
    assert events[-1] == "stop:active"
    assert HostCompositionFailureCode.ROUTE_REMOVAL_FAILED not in runtime.failures
    assert "removal-secret" not in caplog.text


@pytest.mark.asyncio
async def test_stop_removes_routes_and_preserves_reverse_h2_stop_failures() -> None:
    events: list[str] = []
    app, health_route, spa_route = _host()
    first_router, first_route = _router("/plugin/first")
    second_router, second_route = _router("/plugin/second")
    first = _Contribution("first", events, routers=(first_router,))
    second = _Contribution("second", events, routers=(second_router,), stop_error=True)
    runtime = HostPluginRuntime(
        (
            _factory("first", first, events),
            _factory("second", second, events),
        )
    )

    await runtime.start(app)
    await runtime.stop(app)

    assert events[-2:] == ["stop:second", "stop:first"]
    assert first_route not in app.router.routes
    assert second_route not in app.router.routes
    assert health_route in app.router.routes
    assert spa_route in app.router.routes
    assert runtime.registry.failures[-1].stage is PluginLifecycleStage.STOP
    assert runtime.registry.failures[-1].code is PluginFailureCode.STOP_FAILED
