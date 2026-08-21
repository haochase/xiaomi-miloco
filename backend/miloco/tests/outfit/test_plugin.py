# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Composition-root contracts for the optional Outfit plugin."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from miloco.config.settings import OutfitSettings
from miloco.middleware import verify_token
from miloco.outfit import plugin as plugin_module
from miloco.outfit.capability import OutfitProviderStatus
from miloco.outfit.plugin import create_outfit_plugin_factory
from miloco.plugins.primary_person import PrimaryPersonRef, PrimaryPersonResolver
from miloco.plugins.registry import (
    HostPluginRegistry,
    PluginFailureCode,
    PluginLifecycleStage,
)

_SYNTHETIC_DATABASE_PATH = Path(__file__).resolve().parent / "_synthetic" / "outfit.db"


class _RecordingPersonService:
    def __init__(self, *, exists: bool = True, fails: bool = False) -> None:
        self._exists = exists
        self._fails = fails
        self.calls: list[str] = []

    def exists(self, person_id: str) -> bool:
        self.calls.append(person_id)
        if self._fails:
            raise RuntimeError("private lookup failure at C:/private/people.json")
        return self._exists


@dataclass(frozen=True)
class _FakeStorage:
    database_path: Path


@dataclass
class _SideEffectCounters:
    capture: int = 0
    provider: int = 0
    play_text: int = 0


class _TripwireRepository:
    def __init__(self, counters: _SideEffectCounters) -> None:
        self._counters = counters

    def capture_frame(self) -> None:
        self._counters.capture += 1

    def call_provider(self) -> None:
        self._counters.provider += 1

    def play_text(self) -> None:
        self._counters.play_text += 1


class _StorageFactory:
    def __init__(self, *, fails: bool = False) -> None:
        self._fails = fails
        self.calls: list[Path] = []

    def __call__(self, database_path: Path) -> _FakeStorage:
        self.calls.append(database_path)
        if self._fails:
            raise PermissionError("unreadable C:/private/outfit.db")
        return _FakeStorage(database_path)


class _RepositoryFactory:
    def __init__(
        self,
        counters: _SideEffectCounters,
        *,
        fails: bool = False,
    ) -> None:
        self._counters = counters
        self._fails = fails
        self.calls: list[object] = []

    def __call__(self, storage: object) -> _TripwireRepository:
        self.calls.append(storage)
        if self._fails:
            raise RuntimeError("repository failed with private-token")
        return _TripwireRepository(self._counters)


def _require_test_bearer(request: Request) -> None:
    if request.headers.get("Authorization") != "Bearer test-token":
        raise HTTPException(status_code=401, detail="invalid test bearer")


def _plugin_factory(
    *,
    settings: OutfitSettings,
    person_service: _RecordingPersonService,
    database_path: Path = _SYNTHETIC_DATABASE_PATH,
    storage_factory: _StorageFactory | None = None,
    repository_factory: _RepositoryFactory | None = None,
):
    counters = _SideEffectCounters()
    resolved_storage_factory = storage_factory or _StorageFactory()
    resolved_repository_factory = repository_factory or _RepositoryFactory(counters)
    factory = create_outfit_plugin_factory(
        settings=settings,
        primary_person_resolver=PrimaryPersonResolver(settings, person_service),
        database_path=database_path,
        voice_ingress_configured=True,
        camera_allowlisted=False,
        initial_provider_status=OutfitProviderStatus.NEVER_CALLED,
        storage_factory=resolved_storage_factory,
        repository_factory=resolved_repository_factory,
    )
    return factory, resolved_storage_factory, resolved_repository_factory, counters


@pytest.mark.asyncio
async def test_registry_builds_and_publishes_outfit_once_without_get_side_effects() -> (
    None
):
    settings = OutfitSettings(enabled=True, primary_person_id="chase")
    person_service = _RecordingPersonService()
    factory, storage_factory, repository_factory, counters = _plugin_factory(
        settings=settings,
        person_service=person_service,
    )
    registry = HostPluginRegistry((factory,))

    await registry.activate()

    assert factory.id == "outfit_v2"
    assert registry.failures == ()
    assert len(registry.contributions) == 1
    assert len(registry.routers) == 1
    assert registry.panel_capabilities == ("outfit_v2",)
    contribution = registry.contributions[0]
    assert contribution.id == "outfit_v2"
    assert contribution.primary_person == PrimaryPersonRef(person_id="chase")
    assert not hasattr(contribution, "storage")
    assert not hasattr(contribution, "repository")
    with pytest.raises(FrozenInstanceError):
        contribution.primary_person.person_id = "request-owner"  # type: ignore[misc]

    app = FastAPI()
    app.include_router(registry.routers[0])
    app.dependency_overrides[verify_token] = _require_test_bearer
    headers = {"Authorization": "Bearer test-token"}
    with TestClient(app) as client:
        first = client.get("/api/outfit/capability", headers=headers)
        selected = client.request(
            "GET",
            "/api/outfit/capability?owner_person_id=request-owner",
            headers=headers,
            json={"owner_person_id": "body-owner"},
        )
        repeated = client.get("/api/outfit/capability", headers=headers)

    assert first.status_code == selected.status_code == repeated.status_code == 200
    assert selected.json() == repeated.json() == first.json()
    assert contribution.primary_person.person_id == "chase"
    assert person_service.calls == ["chase"]
    assert _SYNTHETIC_DATABASE_PATH.is_absolute()
    assert storage_factory.calls == [_SYNTHETIC_DATABASE_PATH]
    assert len(repository_factory.calls) == 1
    assert counters == _SideEffectCounters()

    await registry.shutdown()
    assert registry.contributions == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("settings", "person_service"),
    (
        (OutfitSettings(), _RecordingPersonService()),
        (OutfitSettings(enabled=True), _RecordingPersonService()),
        (
            OutfitSettings(enabled=True, primary_person_id="unknown-person"),
            _RecordingPersonService(),
        ),
        (
            OutfitSettings(enabled=True, primary_person_id="chase"),
            _RecordingPersonService(exists=False),
        ),
        (
            OutfitSettings(enabled=True, primary_person_id="chase"),
            _RecordingPersonService(fails=True),
        ),
    ),
)
async def test_primary_person_build_failures_publish_nothing(
    settings: OutfitSettings,
    person_service: _RecordingPersonService,
) -> None:
    factory, storage_factory, repository_factory, _ = _plugin_factory(
        settings=settings,
        person_service=person_service,
    )
    registry = HostPluginRegistry((factory,))

    await registry.activate()

    _assert_fixed_build_failure(registry)
    assert storage_factory.calls == []
    assert repository_factory.calls == []


@pytest.mark.asyncio
async def test_relative_database_path_isolated_as_build_failure_before_storage() -> (
    None
):
    factory, storage_factory, repository_factory, _ = _plugin_factory(
        settings=OutfitSettings(enabled=True, primary_person_id="chase"),
        person_service=_RecordingPersonService(),
        database_path=Path("relative/outfit.db"),
    )
    registry = HostPluginRegistry((factory,))

    await registry.activate()

    _assert_fixed_build_failure(registry)
    assert storage_factory.calls == []
    assert repository_factory.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ("storage", "repository"))
async def test_storage_and_repository_failures_publish_nothing(
    failure_stage: str,
) -> None:
    counters = _SideEffectCounters()
    storage_factory = _StorageFactory(fails=failure_stage == "storage")
    repository_factory = _RepositoryFactory(
        counters,
        fails=failure_stage == "repository",
    )
    factory, _, _, _ = _plugin_factory(
        settings=OutfitSettings(enabled=True, primary_person_id="chase"),
        person_service=_RecordingPersonService(),
        storage_factory=storage_factory,
        repository_factory=repository_factory,
    )
    registry = HostPluginRegistry((factory,))

    await registry.activate()

    _assert_fixed_build_failure(registry)
    assert len(storage_factory.calls) == 1
    assert len(repository_factory.calls) == (0 if failure_stage == "storage" else 1)
    assert "private" not in repr(registry.failures)


def test_plugin_module_does_not_import_runtime_device_or_provider_policy() -> None:
    source_path = Path(plugin_module.__file__ or "")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    prohibited_prefixes = (
        "miloco.main",
        "miloco.miot",
        "miloco.outfit.camera_adapter",
        "miloco.outfit.vision_provider",
        "miloco.outfit.visual_service",
        "miloco.outfit.voice_service",
        "miloco.outfit.xiaomi_speaker_adapter",
    )

    assert not any(
        imported == prefix or imported.startswith(f"{prefix}.")
        for imported in imports
        for prefix in prohibited_prefixes
    )


def _assert_fixed_build_failure(registry: HostPluginRegistry) -> None:
    assert registry.contributions == ()
    assert registry.routers == ()
    assert registry.panel_capabilities == ()
    assert len(registry.failures) == 1
    assert registry.failures[0].plugin_id == "outfit_v2"
    assert registry.failures[0].stage is PluginLifecycleStage.BUILD
    assert registry.failures[0].code is PluginFailureCode.BUILD_FAILED
