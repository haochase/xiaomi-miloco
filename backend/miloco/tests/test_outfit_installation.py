# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Tests for the optional Outfit host-installation gate."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from miloco.life.outfit_installation import (
    OutfitInstallConfig,
    OutfitInstallResult,
    OutfitRuntimeContext,
    install_outfit_plugin_if_enabled,
)


def test_disabled_installation_does_not_load_or_mount_plugin() -> None:
    app = FastAPI()
    calls: list[OutfitRuntimeContext] = []

    result = install_outfit_plugin_if_enabled(
        app,
        config=OutfitInstallConfig(),
        installer=lambda _app, runtime: calls.append(runtime),
    )

    assert result == OutfitInstallResult(installed=False, reason="disabled")
    assert calls == []
    assert not hasattr(app.state, "outfit_plugin_installation")


def test_enabled_installation_requires_primary_person_and_absolute_workspace(
    tmp_path,
) -> None:
    app = FastAPI()
    calls: list[OutfitRuntimeContext] = []

    missing_owner = install_outfit_plugin_if_enabled(
        app,
        config=OutfitInstallConfig(enabled=True, workspace_dir=tmp_path),
        installer=lambda _app, runtime: calls.append(runtime),
    )
    relative_workspace = install_outfit_plugin_if_enabled(
        app,
        config=OutfitInstallConfig(
            enabled=True,
            primary_person_id="person-1",
            workspace_dir="storage",
        ),
        installer=lambda _app, runtime: calls.append(runtime),
    )

    assert missing_owner == OutfitInstallResult(
        installed=False, reason="invalid_configuration"
    )
    assert relative_workspace == OutfitInstallResult(
        installed=False, reason="invalid_configuration"
    )
    assert calls == []


def test_enabled_installation_passes_configured_runtime_once(tmp_path) -> None:
    app = FastAPI()
    calls: list[OutfitRuntimeContext] = []
    config = OutfitInstallConfig(
        enabled=True,
        primary_person_id="person-1",
        workspace_dir=tmp_path,
    )

    first = install_outfit_plugin_if_enabled(
        app,
        config=config,
        installer=lambda _app, runtime: calls.append(runtime),
    )
    second = install_outfit_plugin_if_enabled(
        app,
        config=config,
        installer=lambda _app, runtime: calls.append(runtime),
    )

    assert first == OutfitInstallResult(installed=True, reason="installed")
    assert second == first
    assert calls == [
        OutfitRuntimeContext(
            primary_person_id="person-1",
            workspace_dir=tmp_path,
            storage_dir=tmp_path / "outfit",
        )
    ]


def test_failed_installation_preserves_existing_core_routes(tmp_path) -> None:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    result = install_outfit_plugin_if_enabled(
        app,
        config=OutfitInstallConfig(
            enabled=True,
            primary_person_id="person-1",
            workspace_dir=tmp_path,
        ),
        installer=lambda _app, _runtime: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert result == OutfitInstallResult(installed=False, reason="install_failed")
    assert not hasattr(app.state, "outfit_plugin_installation")
    assert TestClient(app).get("/health").json() == {"status": "ok"}
