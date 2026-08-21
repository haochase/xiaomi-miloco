# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Lifecycle contracts for optional host plugin contributions."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import APIRouter
from miloco.plugins.contracts import HostPluginContribution
from miloco.plugins.registry import (
    HostPluginRegistry,
    PluginFactory,
    PluginFailureCode,
    PluginLifecycleStage,
    PluginRegistryActivationError,
)


class LifecycleContribution:
    """In-process contribution with deterministic lifecycle outcomes."""

    def __init__(
        self,
        plugin_id: str,
        events: list[str],
        *,
        start_error: str | None = None,
        stop_error: str | None = None,
        routers: tuple[APIRouter, ...] = (),
        panel_capabilities: tuple[str, ...] = (),
    ) -> None:
        self.id = plugin_id
        self._events = events
        self._start_error = start_error
        self._stop_error = stop_error
        self._routers = routers
        self._panel_capabilities = panel_capabilities

    async def start(self) -> None:
        self._events.append(f"start:{self.id}")
        if self._start_error is not None:
            raise RuntimeError(self._start_error)

    async def stop(self) -> None:
        self._events.append(f"stop:{self.id}")
        if self._stop_error is not None:
            raise RuntimeError(self._stop_error)

    def routers(self) -> tuple[APIRouter, ...]:
        return self._routers

    def panel_capabilities(self) -> tuple[str, ...]:
        return self._panel_capabilities


def _factory(
    plugin_id: str, contribution: HostPluginContribution, events: list[str]
) -> PluginFactory:
    def build() -> HostPluginContribution:
        events.append(f"build:{plugin_id}")
        return contribution

    return PluginFactory(id=plugin_id, build=build)


class SyntheticHost:
    """A test-side host composed from a real registry and core health surface."""

    def __init__(self, factories: tuple[PluginFactory, ...]) -> None:
        self.registry = HostPluginRegistry(factories)
        self._core_health = {"status": "ready"}

    def health(self) -> dict[str, str]:
        return dict(self._core_health)

    async def start(self) -> None:
        await self.registry.activate()

    async def stop(self) -> None:
        await self.registry.shutdown()


@pytest.mark.asyncio
async def test_start_failure_is_not_published_and_later_contribution_activates() -> (
    None
):
    events: list[str] = []
    failed_router = APIRouter()
    active_router = APIRouter()
    failed = LifecycleContribution(
        "failed",
        events,
        start_error="private exception detail",
        routers=(failed_router,),
        panel_capabilities=("failed-panel",),
    )
    active = LifecycleContribution(
        "active",
        events,
        routers=(active_router,),
        panel_capabilities=("active-panel",),
    )
    registry = HostPluginRegistry(
        (
            _factory("failed", failed, events),
            _factory("active", active, events),
        )
    )

    await registry.activate()

    assert events == [
        "build:failed",
        "start:failed",
        "build:active",
        "start:active",
    ]
    assert registry.contributions == (active,)
    assert registry.routers == (active_router,)
    assert registry.panel_capabilities == ("active-panel",)
    assert registry.failures[0].plugin_id == "failed"
    assert registry.failures[0].stage is PluginLifecycleStage.START
    assert registry.failures[0].code is PluginFailureCode.START_FAILED
    assert "private exception detail" not in repr(registry.failures[0])


@pytest.mark.asyncio
async def test_shutdown_stops_active_contributions_in_reverse_and_clears_publications() -> (
    None
):
    events: list[str] = []
    first = LifecycleContribution("first", events)
    second = LifecycleContribution("second", events, stop_error="stop-private-detail")
    third = LifecycleContribution("third", events)
    registry = HostPluginRegistry(
        (
            _factory("first", first, events),
            _factory("second", second, events),
            _factory("third", third, events),
        )
    )

    await registry.activate()
    await registry.shutdown()

    assert events == [
        "build:first",
        "start:first",
        "build:second",
        "start:second",
        "build:third",
        "start:third",
        "stop:third",
        "stop:second",
        "stop:first",
    ]
    assert registry.contributions == ()
    assert registry.routers == ()
    assert registry.panel_capabilities == ()
    assert registry.failures[-1].plugin_id == "second"
    assert registry.failures[-1].stage is PluginLifecycleStage.STOP
    assert registry.failures[-1].code is PluginFailureCode.STOP_FAILED
    assert "stop-private-detail" not in repr(registry.failures[-1])


@pytest.mark.asyncio
async def test_registry_rejects_concurrent_and_duplicate_activation() -> None:
    entered_start = asyncio.Event()
    release_start = asyncio.Event()
    events: list[str] = []

    class BlockingContribution(LifecycleContribution):
        async def start(self) -> None:
            self._events.append(f"start:{self.id}")
            entered_start.set()
            await release_start.wait()

    contribution = BlockingContribution("blocking", events)
    registry = HostPluginRegistry((_factory("blocking", contribution, events),))

    first_activation = asyncio.create_task(registry.activate())
    await entered_start.wait()
    with pytest.raises(PluginRegistryActivationError):
        await registry.activate()

    release_start.set()
    await first_activation

    with pytest.raises(PluginRegistryActivationError):
        await registry.activate()


@pytest.mark.asyncio
async def test_shutdown_waits_for_activation_then_stops_each_success_once_in_reverse() -> (
    None
):
    entered_start = asyncio.Event()
    release_start = asyncio.Event()
    events: list[str] = []

    class BlockingContribution(LifecycleContribution):
        async def start(self) -> None:
            self._events.append(f"start:{self.id}")
            entered_start.set()
            await release_start.wait()

    first = LifecycleContribution("first", events)
    blocking = BlockingContribution("blocking", events)
    registry = HostPluginRegistry(
        (
            _factory("first", first, events),
            _factory("blocking", blocking, events),
        )
    )

    activation = asyncio.create_task(registry.activate())
    await entered_start.wait()
    shutdown = asyncio.create_task(registry.shutdown())
    await asyncio.sleep(0)

    try:
        assert not shutdown.done()
    finally:
        release_start.set()
        await activation
        await shutdown

    assert events == [
        "build:first",
        "start:first",
        "build:blocking",
        "start:blocking",
        "stop:blocking",
        "stop:first",
    ]
    assert events.count("stop:first") == 1
    assert events.count("stop:blocking") == 1
    assert registry.contributions == ()
    assert registry.routers == ()
    assert registry.panel_capabilities == ()


@pytest.mark.asyncio
async def test_synthetic_host_keeps_core_health_through_registry_failures() -> None:
    events: list[str] = []
    self_reported_id = "private-self-reported-id"
    mismatched = LifecycleContribution(self_reported_id, events)
    failed = LifecycleContribution("failed", events, start_error="start detail")
    active = LifecycleContribution("active", events, stop_error="stop detail")

    def broken_build() -> HostPluginContribution:
        events.append("build:broken")
        raise RuntimeError("build detail")

    host = SyntheticHost(
        (
            PluginFactory(id="broken", build=broken_build),
            _factory("mismatch", mismatched, events),
            _factory("failed", failed, events),
            _factory("active", active, events),
        )
    )
    health_before_start = host.health()

    await host.start()
    health_after_start = host.health()
    await host.stop()
    health_after_stop = host.health()

    assert health_before_start == {"status": "ready"}
    assert health_after_start == health_before_start
    assert health_after_stop == health_before_start
    assert [failure.stage for failure in host.registry.failures] == [
        PluginLifecycleStage.BUILD,
        PluginLifecycleStage.BUILD,
        PluginLifecycleStage.START,
        PluginLifecycleStage.STOP,
    ]
    assert self_reported_id not in repr(host.registry.failures[1])
