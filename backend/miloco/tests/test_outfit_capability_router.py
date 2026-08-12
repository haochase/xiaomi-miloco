# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Capability snapshot contracts for the optional Outfit plugin."""

from typing import Annotated

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from miloco.life.outfit_capability_router import build_outfit_capability_router
from miloco.life.outfit_installation import (
    OutfitInstallConfig,
    install_outfit_plugin_if_enabled,
    is_outfit_plugin_installed,
)


def _require_test_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if authorization != "Bearer test-token":
        raise HTTPException(status_code=401, detail="invalid test token")


def _client(app: FastAPI) -> TestClient:
    app.include_router(
        build_outfit_capability_router(app, authenticate=_require_test_token),
        prefix="/api",
    )
    return TestClient(app)


def test_capability_snapshot_requires_authentication_and_hides_uninstalled_plugin() -> (
    None
):
    app = FastAPI()
    client = _client(app)

    missing = client.get("/api/outfit/capabilities")
    response = client.get(
        "/api/outfit/capabilities",
        headers={"Authorization": "Bearer test-token"},
    )

    assert missing.status_code == 401
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert not is_outfit_plugin_installed(app)


def test_capability_snapshot_publishes_only_successfully_installed_outfit_plugin(
    tmp_path,
) -> None:
    app = FastAPI()
    client = _client(app)

    result = install_outfit_plugin_if_enabled(
        app,
        config=OutfitInstallConfig(
            enabled=True,
            primary_person_id="primary-person",
            workspace_dir=tmp_path,
        ),
        installer=lambda _app, _runtime: None,
    )
    response = client.get(
        "/api/outfit/capabilities",
        headers={"Authorization": "Bearer test-token"},
    )

    assert result.installed
    assert is_outfit_plugin_installed(app)
    assert response.status_code == 200
    assert response.json()["data"] == [
        {"id": "outfit_v2", "enabled": True, "api_version": "v1"}
    ]


def test_capability_snapshot_hides_a_failed_optional_installation(tmp_path) -> None:
    app = FastAPI()
    client = _client(app)

    result = install_outfit_plugin_if_enabled(
        app,
        config=OutfitInstallConfig(
            enabled=True,
            primary_person_id="primary-person",
            workspace_dir=tmp_path,
        ),
        installer=lambda _app, _runtime: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    response = client.get(
        "/api/outfit/capabilities",
        headers={"Authorization": "Bearer test-token"},
    )

    assert not result.installed
    assert response.status_code == 200
    assert response.json()["data"] == []
