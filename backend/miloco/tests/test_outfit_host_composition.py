# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Synthetic-host contracts for safe optional Outfit composition."""

from __future__ import annotations

import builtins
import logging
import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import miloco.middleware.auth_middleware as auth_middleware
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from miloco.life.outfit_installation import OutfitInstallConfig, OutfitInstallResult
from miloco.middleware.exception_handler import handle_exception


def _host_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def catch_all_exceptions(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as error:  # noqa: BLE001 - mirrors the official host boundary.
            return handle_exception(request, error)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _configure_official_service_token(monkeypatch) -> dict[str, str]:
    monkeypatch.setattr(
        auth_middleware,
        "get_settings",
        lambda: SimpleNamespace(server=SimpleNamespace(token="test-token")),
    )
    return {"Authorization": "Bearer test-token"}


def _configured_installation(tmp_path: Path) -> OutfitInstallConfig:
    workspace_dir = tmp_path / "miloco-home"
    workspace_dir.mkdir(exist_ok=True)
    return OutfitInstallConfig(
        enabled=True,
        primary_person_id="primary-person",
        workspace_dir=workspace_dir,
    )


def test_disabled_composition_keeps_health_and_hides_outfit_routes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    headers = _configure_official_service_token(monkeypatch)
    app = _host_app()
    imported: list[str] = []
    original_import = builtins.__import__

    def record_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "miloco.life.outfit_authenticated_router":
            imported.append(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(
        sys.modules,
        "miloco.life.outfit_host_composition",
        raising=False,
    )
    monkeypatch.setattr(builtins, "__import__", record_import)
    composition = import_module("miloco.life.outfit_host_composition")

    result = composition.install_outfit_host_composition(
        app,
        config=OutfitInstallConfig(),
        clock_ms=lambda: 2_000,
    )
    client = TestClient(app)

    assert result == OutfitInstallResult(installed=False, reason="disabled")
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/outfit/capabilities").status_code == 404
    assert client.get("/api/outfit/capabilities", headers=headers).status_code == 404
    assert client.get("/api/outfit/moments", headers=headers).status_code == 404
    assert client.get("/outfit/capabilities", headers=headers).status_code == 404
    assert imported == []


def test_successful_composition_uses_official_authentication_and_api_prefix(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from miloco.life.outfit_host_composition import install_outfit_host_composition

    headers = _configure_official_service_token(monkeypatch)
    app = _host_app()

    first = install_outfit_host_composition(
        app,
        config=_configured_installation(tmp_path),
        clock_ms=lambda: 2_000,
    )
    routes_after_first_install = [
        route.path for route in app.routes if route.path == "/api/outfit/moments"
    ]
    second = install_outfit_host_composition(
        app,
        config=_configured_installation(tmp_path),
        clock_ms=lambda: 2_000,
    )
    client = TestClient(app)

    assert first == OutfitInstallResult(installed=True, reason="installed")
    assert second == first
    assert routes_after_first_install == ["/api/outfit/moments"]
    assert [
        route.path for route in app.routes if route.path == "/api/outfit/moments"
    ] == ["/api/outfit/moments"]
    assert client.get("/api/outfit/moments").status_code == 401
    assert client.get("/api/outfit/moments", headers=headers).json()["data"] == []
    assert client.get("/outfit/moments", headers=headers).status_code == 404
    assert client.get("/api/outfit/capabilities", headers=headers).json()["data"] == [
        {"id": "outfit_v2", "enabled": True, "api_version": "v1"}
    ]


def test_failed_storage_initialization_keeps_health_and_hides_capability(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    from miloco.life.outfit_host_composition import install_outfit_host_composition

    headers = _configure_official_service_token(monkeypatch)
    app = _host_app()
    storage_detail = str(tmp_path / "private-storage-error")

    def fail_runtime_build(*_args, **_kwargs) -> None:
        raise RuntimeError(storage_detail)

    import miloco.life.outfit_moment_runtime as runtime_module

    monkeypatch.setattr(
        runtime_module,
        "build_outfit_moment_runtime",
        fail_runtime_build,
    )
    with caplog.at_level(logging.WARNING):
        result = install_outfit_host_composition(
            app,
            config=_configured_installation(tmp_path),
            clock_ms=lambda: 2_000,
        )
    client = TestClient(app)

    assert result == OutfitInstallResult(installed=False, reason="install_failed")
    assert storage_detail not in result.reason
    assert storage_detail not in caplog.text
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/outfit/capabilities", headers=headers).status_code == 404
    assert client.get("/api/outfit/moments", headers=headers).status_code == 404
