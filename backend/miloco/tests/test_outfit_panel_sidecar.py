# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Contracts for the isolated Outfit panel sidecar."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def _static_dir(tmp_path: Path) -> Path:
    static_dir = tmp_path / "panel-static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<html><body><script>window.__MILOCO_TOKEN__ = "
        '"__MILOCO_INJECT_TOKEN_HERE__";</script></body></html>',
        encoding="utf-8",
    )
    return static_dir


def _client(tmp_path: Path) -> TestClient:
    from miloco.life.outfit_panel_sidecar import (
        OutfitPanelSidecarConfig,
        build_outfit_panel_sidecar,
    )

    return TestClient(
        build_outfit_panel_sidecar(
            OutfitPanelSidecarConfig(
                static_dir=_static_dir(tmp_path),
                workspace_dir=tmp_path / "private-workspace",
                primary_person_id="primary-person",
                token="sidecar-test-token",
                browser_username="outfit",
                browser_password="sidecar-browser-password",
            ),
            clock_ms=lambda: 2_000,
        )
    )


def test_sidecar_requires_browser_auth_and_never_injects_api_token(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    unauthenticated_page = client.get("/")
    assert unauthenticated_page.status_code == 401
    assert unauthenticated_page.headers["www-authenticate"].startswith("Basic ")

    page = client.get("/", auth=("outfit", "sidecar-browser-password"))
    assert page.status_code == 200
    assert page.headers["cache-control"] == "private, no-store"
    assert page.headers["x-content-type-options"] == "nosniff"
    assert "sidecar-test-token" not in page.text
    assert "__MILOCO_INJECT_TOKEN_HERE__" in page.text
    assert "__MILOCO_OUTFIT_SIDECAR__ = true" in page.text
    assert client.get("/api/outfit/capabilities").status_code == 401
    assert client.get("/api/outfit/capabilities", headers=_headers()).json()[
        "data"
    ] == [{"id": "outfit_v2", "enabled": True, "api_version": "v1"}]
    assert client.get(
        "/api/outfit/capabilities",
        auth=("outfit", "sidecar-browser-password"),
    ).json()["data"] == [{"id": "outfit_v2", "enabled": True, "api_version": "v1"}]


def test_sidecar_keeps_history_routes_in_the_panel_and_exposes_no_host_api(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    assert (
        client.get(
            "/agents/outfit/moments", auth=("outfit", "sidecar-browser-password")
        ).status_code
        == 200
    )
    assert client.get("/api/devices").status_code == 401
    assert client.get("/api/devices", headers=_headers()).status_code == 404
    assert client.get("/health").json() == {
        "status": "ok",
        "service": "outfit-panel",
    }


def test_sidecar_only_allows_immutable_cache_headers_for_hashed_public_assets(
    tmp_path: Path,
) -> None:
    static_dir = _static_dir(tmp_path)
    assets_dir = static_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "index-abcdef12.js").write_text(
        "console.log('public')", encoding="utf-8"
    )
    (static_dir / "sw.js").write_text(
        "self.addEventListener('fetch', () => {});", encoding="utf-8"
    )

    from miloco.life.outfit_panel_sidecar import (
        OutfitPanelSidecarConfig,
        build_outfit_panel_sidecar,
    )

    client = TestClient(
        build_outfit_panel_sidecar(
            OutfitPanelSidecarConfig(
                static_dir=static_dir,
                workspace_dir=tmp_path / "private-workspace",
                primary_person_id="primary-person",
                token="sidecar-test-token",
                browser_username="outfit",
                browser_password="sidecar-browser-password",
            )
        )
    )

    asset = client.get(
        "/assets/index-abcdef12.js", auth=("outfit", "sidecar-browser-password")
    )
    service_worker = client.get("/sw.js", auth=("outfit", "sidecar-browser-password"))

    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert asset.headers["x-content-type-options"] == "nosniff"
    assert service_worker.headers["cache-control"] == "private, no-store"


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer sidecar-test-token"}
