# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Explicit composition root for the optional Outfit plugin."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter

from miloco.config.settings import OutfitSettings
from miloco.outfit.capability import OutfitCapabilityState, OutfitProviderStatus
from miloco.outfit.capability_router import create_outfit_capability_router
from miloco.outfit.storage import OutfitStorage
from miloco.outfit.wardrobe_repo import WardrobeRepository
from miloco.plugins.primary_person import PrimaryPersonRef, PrimaryPersonResolver
from miloco.plugins.registry import PluginFactory

StorageFactory = Callable[[Path], OutfitStorage]
RepositoryFactory = Callable[[OutfitStorage], WardrobeRepository]


class OutfitPluginContribution:
    """Own private Outfit dependencies and publish only stable host contracts."""

    id = "outfit_v2"
    __slots__ = ("_primary_person", "_storage", "_repository", "_router")

    def __init__(
        self,
        *,
        primary_person: PrimaryPersonRef,
        storage: OutfitStorage,
        repository: WardrobeRepository,
        router: APIRouter,
    ) -> None:
        self._primary_person = primary_person
        self._storage = storage
        self._repository = repository
        self._router = router

    @property
    def primary_person(self) -> PrimaryPersonRef:
        """Expose only the immutable H1 owner reference for later composition."""

        return self._primary_person

    async def start(self) -> None:
        """Start without background work."""

    async def stop(self) -> None:
        """Stop without background work."""

    def routers(self) -> tuple[APIRouter, ...]:
        return (self._router,)

    def panel_capabilities(self) -> tuple[str, ...]:
        return (self.id,)


def create_outfit_plugin_factory(
    *,
    settings: OutfitSettings,
    primary_person_resolver: PrimaryPersonResolver,
    database_path: str | Path,
    voice_ingress_configured: bool,
    camera_allowlisted: bool,
    initial_provider_status: OutfitProviderStatus,
    storage_factory: StorageFactory = OutfitStorage,
    repository_factory: RepositoryFactory = WardrobeRepository,
) -> PluginFactory:
    """Create the H2 factory while deferring every fallible build step to H2."""

    def build() -> OutfitPluginContribution:
        primary_person = primary_person_resolver.resolve()
        if (
            not settings.enabled
            or settings.primary_person_id != primary_person.person_id
        ):
            raise ValueError("Outfit primary person configuration is inconsistent")

        resolved_database_path = Path(database_path)
        if not resolved_database_path.is_absolute():
            raise ValueError("Outfit storage database_path must be absolute")

        storage = storage_factory(resolved_database_path)
        repository = repository_factory(storage)
        capability_state = OutfitCapabilityState(
            enabled=True,
            primary_person_configured=True,
            storage_ready=True,
            voice_ingress_configured=voice_ingress_configured,
            camera_allowlisted=camera_allowlisted,
            last_provider_status=initial_provider_status,
        )
        router = create_outfit_capability_router(state=capability_state)
        return OutfitPluginContribution(
            primary_person=primary_person,
            storage=storage,
            repository=repository,
            router=router,
        )

    return PluginFactory(id="outfit_v2", build=build)
