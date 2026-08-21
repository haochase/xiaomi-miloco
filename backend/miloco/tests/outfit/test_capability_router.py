# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Authenticated zero-side-effect HTTP capability contracts for Outfit."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from miloco.middleware import verify_token
from miloco.outfit import capability as capability_module
from miloco.outfit import capability_router as capability_router_module
from miloco.outfit.capability import OutfitCapabilityState, OutfitProviderStatus
from miloco.outfit.capability_router import create_outfit_capability_router


@dataclass
class _SideEffectCounters:
    capture: int = 0
    provider: int = 0
    play_text: int = 0


def _require_test_bearer(request: Request) -> None:
    if request.headers.get("Authorization") != "Bearer test-token":
        raise HTTPException(status_code=401, detail="invalid test bearer")


def _app() -> tuple[FastAPI, _SideEffectCounters]:
    state = OutfitCapabilityState(
        enabled=True,
        primary_person_configured=True,
        storage_ready=True,
        voice_ingress_configured=False,
        camera_allowlisted=True,
        last_provider_status=OutfitProviderStatus.NOT_CONFIGURED,
    )
    counters = _SideEffectCounters()
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "ok": True,
            "synthetic_core": "unchanged",
            "side_effects": counters.__dict__.copy(),
        }

    app.include_router(create_outfit_capability_router(state=state))
    app.dependency_overrides[verify_token] = _require_test_bearer
    return app, counters


def test_capability_get_requires_bearer_and_returns_exact_private_snapshot() -> None:
    app, _ = _app()

    with TestClient(app) as client:
        assert client.get("/api/outfit/capability").status_code == 401
        response = client.get(
            "/api/outfit/capability",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "primary_person_configured": True,
        "storage_ready": True,
        "voice_ingress_configured": False,
        "camera_allowlisted": True,
        "last_provider_status": "not_configured",
    }
    assert response.headers["cache-control"] == "private, no-store"
    assert set(response.json()) == {
        "enabled",
        "primary_person_configured",
        "storage_ready",
        "voice_ingress_configured",
        "camera_allowlisted",
        "last_provider_status",
    }


def test_repeated_get_ignores_selectors_and_leaves_core_and_effects_unchanged() -> None:
    app, counters = _app()
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(app) as client:
        health_before = client.get("/health").json()
        baseline = client.get("/api/outfit/capability", headers=headers).json()
        query_selected = client.get(
            "/api/outfit/capability?owner_person_id=other&device_id=camera-9",
            headers=headers,
        ).json()
        body_selected = client.request(
            "GET",
            "/api/outfit/capability",
            headers=headers,
            json={
                "owner_person_id": "other",
                "database_path": "C:/private/outfit.db",
                "provider_model": "private-model",
            },
        ).json()
        health_after = client.get("/health").json()

    assert query_selected == baseline
    assert body_selected == baseline
    assert health_after == health_before
    assert counters == _SideEffectCounters()

    operation = app.openapi()["paths"]["/api/outfit/capability"]["get"]
    assert "requestBody" not in operation
    assert operation.get("parameters", []) == []


def test_capability_modules_do_not_import_runtime_or_policy_dependencies() -> None:
    prohibited_prefixes = (
        "miloco.main",
        "miloco.miot",
        "miloco.outfit.camera_adapter",
        "miloco.outfit.vision_provider",
        "miloco.outfit.visual_service",
        "miloco.outfit.voice_service",
        "miloco.outfit.xiaomi_speaker_adapter",
    )

    for module in (capability_module, capability_router_module):
        source_path = Path(module.__file__ or "")
        imports = _imports_from(source_path)
        assert not any(
            imported == prefix or imported.startswith(f"{prefix}.")
            for imported in imports
            for prefix in prohibited_prefixes
        )


def _imports_from(source_path: Path) -> set[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
