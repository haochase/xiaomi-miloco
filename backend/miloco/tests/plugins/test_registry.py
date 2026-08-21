# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Contracts for the neutral, in-process plugin registry."""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path

import miloco.plugins as plugins
import pytest
from fastapi import APIRouter
from miloco.plugins.contracts import HostPluginContribution
from miloco.plugins.registry import (
    HostPluginRegistry,
    PluginFactory,
    PluginFailureCode,
    PluginLifecycleStage,
)


class RecordingContribution:
    """A small in-process contribution used to observe registry behavior."""

    def __init__(
        self,
        plugin_id: str,
        events: list[str],
        *,
        routers: tuple[APIRouter, ...] = (),
        panel_capabilities: tuple[str, ...] = (),
    ) -> None:
        self.id = plugin_id
        self._events = events
        self._routers = routers
        self._panel_capabilities = panel_capabilities

    async def start(self) -> None:
        self._events.append(f"start:{self.id}")

    async def stop(self) -> None:
        self._events.append(f"stop:{self.id}")

    def routers(self) -> tuple[APIRouter, ...]:
        return self._routers

    def panel_capabilities(self) -> tuple[str, ...]:
        return self._panel_capabilities


class PublicationContribution(RecordingContribution):
    """A started contribution whose publication behavior is independently controlled."""

    def __init__(
        self,
        plugin_id: str,
        events: list[str],
        *,
        routers_result: object = (),
        capabilities_result: object = (),
        routers_error: bool = False,
        capabilities_error: bool = False,
        stop_error: bool = False,
    ) -> None:
        super().__init__(plugin_id, events)
        self._routers_result = routers_result
        self._capabilities_result = capabilities_result
        self._routers_error = routers_error
        self._capabilities_error = capabilities_error
        self._stop_error = stop_error
        self.routers_calls = 0
        self.capabilities_calls = 0

    async def stop(self) -> None:
        self._events.append(f"stop:{self.id}")
        if self._stop_error:
            raise RuntimeError("synthetic stop failure")

    def routers(self) -> object:
        self.routers_calls += 1
        self._events.append(f"routers:{self.id}")
        if self._routers_error:
            raise RuntimeError("synthetic routers failure")
        return self._routers_result

    def panel_capabilities(self) -> object:
        self.capabilities_calls += 1
        self._events.append(f"capabilities:{self.id}")
        if self._capabilities_error:
            raise RuntimeError("synthetic capabilities failure")
        return self._capabilities_result


def _factory(
    plugin_id: str, contribution: HostPluginContribution, events: list[str]
) -> PluginFactory:
    def build() -> HostPluginContribution:
        events.append(f"build:{plugin_id}")
        return contribution

    return PluginFactory(id=plugin_id, build=build)


@pytest.mark.asyncio
async def test_registry_activates_and_publishes_in_supplied_factory_order() -> None:
    events: list[str] = []
    later_router = APIRouter()
    earlier_router = APIRouter()
    later = RecordingContribution(
        "later",
        events,
        routers=(later_router,),
        panel_capabilities=("later-panel",),
    )
    earlier = RecordingContribution(
        "earlier",
        events,
        routers=(earlier_router,),
        panel_capabilities=("earlier-panel",),
    )
    registry = HostPluginRegistry(
        (
            _factory("later", later, events),
            _factory("earlier", earlier, events),
        )
    )

    await registry.activate()

    assert events == [
        "build:later",
        "start:later",
        "build:earlier",
        "start:earlier",
    ]
    assert registry.contributions == (later, earlier)
    assert registry.routers == (later_router, earlier_router)
    assert registry.panel_capabilities == ("later-panel", "earlier-panel")
    assert registry.failures == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("routers_result", "capabilities_result"),
    [
        ([APIRouter()], ("panel",)),
        ((object(),), ("panel",)),
        ((APIRouter(),), ["panel"]),
        ((APIRouter(),), ("",)),
        ((APIRouter(),), (" unstable ",)),
        ((APIRouter(),), (42,)),
    ],
)
async def test_registry_isolates_invalid_publication_and_continues(
    routers_result: object,
    capabilities_result: object,
) -> None:
    events: list[str] = []
    rejected = PublicationContribution(
        "rejected",
        events,
        routers_result=routers_result,
        capabilities_result=capabilities_result,
    )
    active_router = APIRouter()
    active = PublicationContribution(
        "active",
        events,
        routers_result=(active_router,),
        capabilities_result=("active-panel",),
    )
    registry = HostPluginRegistry(
        (
            _factory("rejected", rejected, events),
            _factory("active", active, events),
        )
    )

    await registry.activate()

    assert events.index("stop:rejected") < events.index("build:active")
    assert registry.contributions == (active,)
    assert registry.routers == (active_router,)
    assert registry.panel_capabilities == ("active-panel",)
    assert registry.failures == (registry.failures[0],)
    assert registry.failures[0].plugin_id == "rejected"
    assert registry.failures[0].stage is PluginLifecycleStage.PUBLISH
    assert registry.failures[0].code is PluginFailureCode.PUBLISH_FAILED


@pytest.mark.asyncio
async def test_registry_isolates_publication_method_failure_and_records_stop_failure() -> (
    None
):
    events: list[str] = []
    rejected = PublicationContribution(
        "rejected",
        events,
        routers_error=True,
        stop_error=True,
    )
    active = PublicationContribution(
        "active",
        events,
        routers_result=(),
        capabilities_result=(),
    )
    registry = HostPluginRegistry(
        (
            _factory("rejected", rejected, events),
            _factory("active", active, events),
        )
    )

    await registry.activate()

    assert events.index("stop:rejected") < events.index("build:active")
    assert registry.contributions == (active,)
    assert [(failure.stage, failure.code) for failure in registry.failures] == [
        (PluginLifecycleStage.PUBLISH, PluginFailureCode.PUBLISH_FAILED),
        (PluginLifecycleStage.STOP, PluginFailureCode.STOP_FAILED),
    ]


@pytest.mark.asyncio
async def test_registry_caches_immutable_publication_snapshots() -> None:
    events: list[str] = []
    router = APIRouter()
    contribution = PublicationContribution(
        "cached",
        events,
        routers_result=(router,),
        capabilities_result=("cached-panel",),
    )
    registry = HostPluginRegistry((_factory("cached", contribution, events),))

    await registry.activate()

    assert registry.contributions is registry.contributions
    assert registry.routers is registry.routers
    assert registry.panel_capabilities is registry.panel_capabilities
    assert registry.routers == (router,)
    assert registry.panel_capabilities == ("cached-panel",)
    assert contribution.routers_calls == 1
    assert contribution.capabilities_calls == 1


@pytest.mark.asyncio
async def test_build_failure_is_recorded_without_blocking_later_factories() -> None:
    events: list[str] = []
    secret = "C:/private/config/secret-value"
    active = RecordingContribution("active", events)

    def build_that_fails() -> HostPluginContribution:
        events.append("build:broken")
        raise RuntimeError(secret)

    registry = HostPluginRegistry(
        (
            PluginFactory(id="broken", build=build_that_fails),
            _factory("active", active, events),
        )
    )

    await registry.activate()

    assert events == ["build:broken", "build:active", "start:active"]
    assert registry.contributions == (active,)
    assert registry.failures[0].plugin_id == "broken"
    assert registry.failures[0].stage is PluginLifecycleStage.BUILD
    assert registry.failures[0].code is PluginFailureCode.BUILD_FAILED
    assert tuple(field.name for field in fields(registry.failures[0])) == (
        "plugin_id",
        "stage",
        "code",
    )
    assert secret not in repr(registry.failures[0])
    assert secret not in str(registry.failures[0])


@pytest.mark.parametrize("plugin_id", ["", " ", "\t"])
def test_registry_rejects_blank_factory_ids_before_activation(plugin_id: str) -> None:
    build_calls: list[str] = []

    def build() -> HostPluginContribution:
        build_calls.append("called")
        raise AssertionError("a blank factory must never be built")

    with pytest.raises(ValueError, match="factory"):
        HostPluginRegistry((PluginFactory(id=plugin_id, build=build),))

    assert build_calls == []


def test_registry_rejects_duplicate_factory_ids_before_activation() -> None:
    events: list[str] = []
    first = RecordingContribution("first", events)
    second = RecordingContribution("second", events)

    with pytest.raises(ValueError, match="factory"):
        HostPluginRegistry(
            (
                _factory("same-id", first, events),
                _factory("same-id", second, events),
            )
        )

    assert events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reported_id", ["", " \t"])
async def test_blank_contribution_identity_is_recorded_before_start_and_later_factory_activates(
    reported_id: str,
) -> None:
    events: list[str] = []
    rejected = RecordingContribution("placeholder", events)
    rejected.id = reported_id
    active = RecordingContribution("active", events)
    registry = HostPluginRegistry(
        (
            _factory("rejected", rejected, events),
            _factory("active", active, events),
        )
    )

    await registry.activate()

    assert events == ["build:rejected", "build:active", "start:active"]
    assert registry.contributions == (active,)
    assert len(registry.failures) == 1
    assert registry.failures[0].plugin_id == "rejected"
    assert registry.failures[0].stage is PluginLifecycleStage.BUILD
    assert registry.failures[0].code is PluginFailureCode.BUILD_FAILED


@pytest.mark.asyncio
async def test_non_string_contribution_identity_records_only_factory_build_failure() -> (
    None
):
    events: list[str] = []
    reported_id = 42
    rejected = RecordingContribution("placeholder", events)
    rejected.id = reported_id
    active = RecordingContribution("active", events)
    registry = HostPluginRegistry(
        (
            _factory("rejected", rejected, events),
            _factory("active", active, events),
        )
    )

    await registry.activate()

    assert events == ["build:rejected", "build:active", "start:active"]
    assert registry.contributions == (active,)
    assert len(registry.failures) == 1
    failure = registry.failures[0]
    assert failure.plugin_id == "rejected"
    assert failure.stage is PluginLifecycleStage.BUILD
    assert failure.code is PluginFailureCode.BUILD_FAILED
    assert str(reported_id) not in repr(failure)
    assert str(reported_id) not in str(failure)


@pytest.mark.asyncio
async def test_mismatched_contribution_identity_records_factory_only_and_continues() -> (
    None
):
    events: list[str] = []
    self_reported_id = "private-self-reported-id"
    rejected = RecordingContribution(self_reported_id, events)
    active = RecordingContribution("active", events)
    registry = HostPluginRegistry(
        (
            _factory("expected-factory-id", rejected, events),
            _factory("active", active, events),
        )
    )

    await registry.activate()

    assert events == [
        "build:expected-factory-id",
        "build:active",
        "start:active",
    ]
    assert registry.contributions == (active,)
    assert len(registry.failures) == 1
    failure = registry.failures[0]
    assert failure.plugin_id == "expected-factory-id"
    assert failure.stage is PluginLifecycleStage.BUILD
    assert failure.code is PluginFailureCode.BUILD_FAILED
    assert self_reported_id not in repr(failure)
    assert self_reported_id not in str(failure)


@pytest.mark.asyncio
async def test_duplicate_contribution_identity_is_not_started_and_later_factory_activates() -> (
    None
):
    events: list[str] = []
    first = RecordingContribution("first", events)
    duplicate = RecordingContribution("first", events)
    active = RecordingContribution("active", events)
    registry = HostPluginRegistry(
        (
            _factory("first", first, events),
            _factory("second", duplicate, events),
            _factory("active", active, events),
        )
    )

    await registry.activate()

    assert events == [
        "build:first",
        "start:first",
        "build:second",
        "build:active",
        "start:active",
    ]
    assert registry.contributions == (first, active)
    assert len(registry.failures) == 1
    failure = registry.failures[0]
    assert failure.plugin_id == "second"
    assert failure.stage is PluginLifecycleStage.BUILD
    assert failure.code is PluginFailureCode.BUILD_FAILED
    assert "first" not in repr(failure)
    assert "first" not in str(failure)


@pytest.mark.parametrize(
    "untrusted_entry",
    ["miloco.outfit.plugins", "https://example.invalid/plugin.py"],
)
def test_registry_accepts_only_explicit_in_process_factory_entries(
    untrusted_entry: str,
) -> None:
    with pytest.raises(ValueError, match="factory"):
        HostPluginRegistry((untrusted_entry,))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "container",
    [
        lambda factory: [factory],
        lambda factory: {factory},
        lambda factory: {factory.id: factory},
        lambda factory: (entry for entry in (factory,)),
    ],
    ids=["list", "set", "dict", "generator"],
)
def test_registry_rejects_non_tuple_factory_containers(
    container: Callable[[PluginFactory], object],
) -> None:
    events: list[str] = []
    contribution = RecordingContribution("ordered", events)
    factory = _factory("ordered", contribution, events)

    with pytest.raises(ValueError, match="tuple"):
        HostPluginRegistry(container(factory))  # type: ignore[arg-type]

    assert events == []


def test_generic_plugins_modules_remain_neutral_and_avoid_dynamic_loading() -> None:
    plugins_dir = Path(__file__).parents[2] / "src" / "miloco" / "plugins"
    prohibited_prefixes = (
        "miloco.outfit",
        "miloco.main",
        "miloco.observability",
        "miloco.miot",
        "importlib",
    )

    for module_name in ("__init__.py", "contracts.py", "registry.py"):
        source = (plugins_dir / module_name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }

        assert not any(
            imported == prefix or imported.startswith(f"{prefix}.")
            for imported in imports
            for prefix in prohibited_prefixes
        )


def test_plugins_package_exports_only_neutral_contracts_and_registry_types() -> None:
    assert plugins.__all__ == [
        "HostPluginContribution",
        "HostPluginRegistry",
        "PluginFactory",
        "PluginFailure",
        "PluginFailureCode",
        "PluginLifecycleStage",
        "PluginRegistryActivationError",
    ]
