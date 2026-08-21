# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Deterministic lifecycle management for optional in-process plugins."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from fastapi import APIRouter

from miloco.plugins.contracts import HostPluginContribution


class PluginLifecycleStage(str, Enum):
    """Finite stages at which optional contributions can fail."""

    BUILD = "build"
    START = "start"
    PUBLISH = "publish"
    STOP = "stop"


class PluginFailureCode(str, Enum):
    """Fixed, low-sensitive lifecycle failure codes."""

    BUILD_FAILED = "build_failed"
    START_FAILED = "start_failed"
    PUBLISH_FAILED = "publish_failed"
    STOP_FAILED = "stop_failed"


@dataclass(frozen=True, slots=True)
class PluginFactory:
    """An explicit, in-process factory supplied at host build time."""

    id: str
    build: Callable[[], HostPluginContribution]


@dataclass(frozen=True, slots=True)
class PluginFailure:
    """A safe lifecycle outcome without exception details."""

    plugin_id: str
    stage: PluginLifecycleStage
    code: PluginFailureCode


@dataclass(frozen=True, slots=True)
class _ActivatedContribution:
    """A started contribution with publication data captured exactly once."""

    plugin_id: str
    contribution: HostPluginContribution
    routers: tuple[APIRouter, ...]
    panel_capabilities: tuple[str, ...]


class PluginRegistryActivationError(RuntimeError):
    """Raised when a one-shot registry is activated more than once."""

    def __init__(self) -> None:
        super().__init__("plugin registry activation was already attempted")


class HostPluginRegistry:
    """Activate supplied optional contributions in their declared order."""

    def __init__(self, factories: tuple[PluginFactory, ...]) -> None:
        if not isinstance(factories, tuple):
            raise ValueError("plugin factories must be supplied as a tuple")
        self._factories = factories
        self._validate_factories()
        self._active: list[_ActivatedContribution] = []
        self._contributions_snapshot: tuple[HostPluginContribution, ...] = ()
        self._routers_snapshot: tuple[APIRouter, ...] = ()
        self._panel_capabilities_snapshot: tuple[str, ...] = ()
        self._failures: tuple[PluginFailure, ...] = ()
        self._lifecycle_lock = asyncio.Lock()
        self._activation_started = False
        self._shutdown_requested = False
        self._shutdown_completed = False

    @property
    def contributions(self) -> tuple[HostPluginContribution, ...]:
        """Published contributions in successful activation order."""

        return self._contributions_snapshot

    @property
    def routers(self) -> tuple[APIRouter, ...]:
        """Published routers in successful activation order."""

        return self._routers_snapshot

    @property
    def panel_capabilities(self) -> tuple[str, ...]:
        """Published panel capabilities in successful activation order."""

        return self._panel_capabilities_snapshot

    @property
    def failures(self) -> tuple[PluginFailure, ...]:
        """Low-sensitive lifecycle failures in occurrence order."""

        return self._failures

    async def activate(self) -> None:
        """Build and start every optional contribution once."""

        if self._activation_started or self._shutdown_requested:
            raise PluginRegistryActivationError()
        self._activation_started = True

        async with self._lifecycle_lock:
            contribution_ids: set[str] = set()
            for factory in self._factories:
                try:
                    contribution = factory.build()
                except Exception:
                    self._record_failure(
                        factory.id,
                        PluginLifecycleStage.BUILD,
                        PluginFailureCode.BUILD_FAILED,
                    )
                    continue

                if not self._has_valid_contribution_identity(
                    factory.id, contribution, contribution_ids
                ):
                    self._record_failure(
                        factory.id,
                        PluginLifecycleStage.BUILD,
                        PluginFailureCode.BUILD_FAILED,
                    )
                    continue

                try:
                    await contribution.start()
                except Exception:
                    self._record_failure(
                        factory.id,
                        PluginLifecycleStage.START,
                        PluginFailureCode.START_FAILED,
                    )
                    continue

                publication = self._read_publication(contribution)
                if publication is None:
                    self._record_failure(
                        factory.id,
                        PluginLifecycleStage.PUBLISH,
                        PluginFailureCode.PUBLISH_FAILED,
                    )
                    await self._isolate_failed_publication(factory.id, contribution)
                    continue

                routers, panel_capabilities = publication
                self._active.append(
                    _ActivatedContribution(
                        plugin_id=factory.id,
                        contribution=contribution,
                        routers=routers,
                        panel_capabilities=panel_capabilities,
                    )
                )
            self._refresh_publication_snapshots()

    async def shutdown(self) -> None:
        """Stop active contributions in reverse successful-start order."""

        self._shutdown_requested = True
        async with self._lifecycle_lock:
            if self._shutdown_completed:
                return
            for active in reversed(self._active):
                try:
                    await active.contribution.stop()
                except Exception:
                    self._record_failure(
                        active.plugin_id,
                        PluginLifecycleStage.STOP,
                        PluginFailureCode.STOP_FAILED,
                    )
            self._active.clear()
            self._refresh_publication_snapshots()
            self._shutdown_completed = True

    def _validate_factories(self) -> None:
        factory_ids: set[str] = set()
        for factory in self._factories:
            if not isinstance(factory, PluginFactory):
                raise ValueError(
                    "plugin factory entries must be explicit PluginFactory instances"
                )
            if not isinstance(factory.id, str) or not factory.id.strip():
                raise ValueError("plugin factory IDs must be non-blank")
            if not callable(factory.build):
                raise ValueError("plugin factory build must be callable")
            if factory.id in factory_ids:
                raise ValueError("plugin factory IDs must be unique")
            factory_ids.add(factory.id)

    def _has_valid_contribution_identity(
        self,
        factory_id: str,
        contribution: HostPluginContribution,
        contribution_ids: set[str],
    ) -> bool:
        try:
            contribution_id = contribution.id
        except Exception:
            return False
        if not isinstance(contribution_id, str) or not contribution_id.strip():
            return False
        if contribution_id != factory_id or contribution_id in contribution_ids:
            return False
        contribution_ids.add(contribution_id)
        return True

    def _read_publication(
        self,
        contribution: HostPluginContribution,
    ) -> tuple[tuple[APIRouter, ...], tuple[str, ...]] | None:
        try:
            routers = contribution.routers()
            panel_capabilities = contribution.panel_capabilities()
        except Exception:
            return None
        if not isinstance(routers, tuple) or not all(
            isinstance(router, APIRouter) for router in routers
        ):
            return None
        if not isinstance(panel_capabilities, tuple) or not all(
            type(capability) is str
            and bool(capability)
            and capability == capability.strip()
            for capability in panel_capabilities
        ):
            return None
        return routers, panel_capabilities

    async def _isolate_failed_publication(
        self,
        plugin_id: str,
        contribution: HostPluginContribution,
    ) -> None:
        try:
            await contribution.stop()
        except Exception:
            self._record_failure(
                plugin_id,
                PluginLifecycleStage.STOP,
                PluginFailureCode.STOP_FAILED,
            )

    def _refresh_publication_snapshots(self) -> None:
        self._contributions_snapshot = tuple(
            active.contribution for active in self._active
        )
        self._routers_snapshot = tuple(
            router for active in self._active for router in active.routers
        )
        self._panel_capabilities_snapshot = tuple(
            capability
            for active in self._active
            for capability in active.panel_capabilities
        )

    def _record_failure(
        self,
        plugin_id: str,
        stage: PluginLifecycleStage,
        code: PluginFailureCode,
    ) -> None:
        self._failures += (PluginFailure(plugin_id=plugin_id, stage=stage, code=code),)
