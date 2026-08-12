# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Isolated, authenticated web sidecar for the optional Outfit panel.

The sidecar deliberately does not import ``miloco.main``.  It can serve the
same compiled control-panel SPA while exposing only the configured Outfit
plugin surface, on a separate port and in a separate workspace.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from miloco.life.outfit_host_composition import install_outfit_host_composition
from miloco.life.outfit_installation import OutfitInstallConfig

_INDEX_NAME = "index.html"
_TOKEN_PLACEHOLDER = 'window.__MILOCO_TOKEN__ = "__MILOCO_INJECT_TOKEN_HERE__";'
_NO_STORE_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}
_IMMUTABLE_PUBLIC_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
    "X-Content-Type-Options": "nosniff",
}
_HASHED_PUBLIC_ASSET = re.compile(r"^assets/.+-[A-Za-z0-9_-]{8,}\.(?:js|css)$")
_BROWSER_AUTH_HEADERS = {"WWW-Authenticate": 'Basic realm="Miloco Outfit"'}


@dataclass(frozen=True)
class OutfitPanelSidecarConfig:
    """Explicit non-device configuration required by the panel sidecar."""

    static_dir: Path | str
    workspace_dir: Path | str
    primary_person_id: str
    token: str
    browser_username: str
    browser_password: str


def build_outfit_panel_sidecar(
    config: OutfitPanelSidecarConfig,
    *,
    clock_ms: Callable[[], int] | None = None,
) -> FastAPI:
    """Build an authenticated sidecar without loading host-control routes."""
    static_dir, workspace_dir, owner, token, browser_username, browser_password = (
        _resolve_config(config)
    )
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def authenticate(
        authorization: str | None = Header(default=None),
    ) -> None:
        if not _is_api_authorized(
            authorization,
            token=token,
            browser_username=browser_username,
            browser_password=browser_password,
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid sidecar credentials",
                headers=_BROWSER_AUTH_HEADERS,
            )

    @app.middleware("http")
    async def require_browser_auth(request: Request, call_next: Callable) -> Response:
        if request.url.path == "/health" or request.url.path.startswith("/api/"):
            return await call_next(request)
        if not _matches_basic_auth(
            request.headers.get("authorization"),
            username=browser_username,
            password=browser_password,
        ):
            return Response(status_code=401, headers=_BROWSER_AUTH_HEADERS)
        return await call_next(request)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "outfit-panel"}

    result = install_outfit_host_composition(
        app,
        config=OutfitInstallConfig(
            enabled=True,
            primary_person_id=owner,
            workspace_dir=workspace_dir,
        ),
        clock_ms=clock_ms or _clock_ms,
        authenticate=authenticate,
    )
    if not result.installed:
        raise RuntimeError(f"Outfit sidecar installation failed: {result.reason}")

    @app.get(
        "/api/{unmatched_path:path}",
        include_in_schema=False,
        dependencies=[Depends(authenticate)],
    )
    def unknown_api(unmatched_path: str) -> None:
        raise HTTPException(status_code=404, detail="Sidecar API route not found")

    @app.get("/{panel_path:path}", include_in_schema=False)
    def panel(panel_path: str) -> Response:
        asset = _safe_asset(static_dir, panel_path)
        if asset is not None:
            return FileResponse(asset, headers=_asset_headers(panel_path))
        return _panel_entry(static_dir)

    return app


def _resolve_config(
    config: OutfitPanelSidecarConfig,
) -> tuple[Path, Path, str, str, str, str]:
    static_dir = Path(config.static_dir).resolve()
    workspace_dir = Path(config.workspace_dir)
    owner = config.primary_person_id.strip()
    token = config.token.strip()
    browser_username = config.browser_username.strip()
    browser_password = config.browser_password.strip()
    if not static_dir.is_dir() or not (static_dir / _INDEX_NAME).is_file():
        raise ValueError("sidecar static_dir must contain index.html")
    if not workspace_dir.is_absolute():
        raise ValueError("sidecar workspace_dir must be absolute")
    if not owner:
        raise ValueError("sidecar primary_person_id must not be blank")
    if not token:
        raise ValueError("sidecar token must not be blank")
    if not browser_username:
        raise ValueError("sidecar browser_username must not be blank")
    if not browser_password:
        raise ValueError("sidecar browser_password must not be blank")
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return (
        static_dir,
        workspace_dir,
        owner,
        token,
        browser_username,
        browser_password,
    )


def _safe_asset(static_dir: Path, panel_path: str) -> Path | None:
    if not panel_path or panel_path.endswith("/"):
        return None
    candidate = (static_dir / panel_path).resolve()
    if candidate == static_dir or static_dir not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def _panel_entry(static_dir: Path) -> HTMLResponse:
    html = (static_dir / _INDEX_NAME).read_text(encoding="utf-8")
    if _TOKEN_PLACEHOLDER not in html:
        raise RuntimeError("sidecar index.html has no Miloco token placeholder")
    marker = "window.__MILOCO_OUTFIT_SIDECAR__ = true;"
    html = html.replace(_TOKEN_PLACEHOLDER, f"{_TOKEN_PLACEHOLDER}\n      {marker}", 1)
    return HTMLResponse(html, headers=_NO_STORE_HEADERS)


def _is_api_authorized(
    authorization: str | None,
    *,
    token: str,
    browser_username: str,
    browser_password: str,
) -> bool:
    expected_bearer = f"Bearer {token}"
    return bool(
        authorization
        and (
            secrets.compare_digest(authorization, expected_bearer)
            or _matches_basic_auth(
                authorization,
                username=browser_username,
                password=browser_password,
            )
        )
    )


def _matches_basic_auth(
    authorization: str | None,
    *,
    username: str,
    password: str,
) -> bool:
    expected = base64.b64encode(f"{username}:{password}".encode()).decode()
    return bool(
        authorization and secrets.compare_digest(authorization, f"Basic {expected}")
    )


def _asset_headers(panel_path: str) -> dict[str, str]:
    """Cache only immutable public build assets, never panel entries or APIs."""
    normalized = panel_path.replace("\\", "/")
    if (
        _HASHED_PUBLIC_ASSET.fullmatch(normalized)
        or normalized.startswith("fonts/")
        or normalized.startswith("icons/")
    ):
        return _IMMUTABLE_PUBLIC_HEADERS
    return _NO_STORE_HEADERS


def _clock_ms() -> int:
    return int(time.time() * 1_000)


def start_outfit_panel_sidecar() -> None:
    """Run with explicit environment variables, keeping the token off argv."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=1811, type=int)
    args = parser.parse_args()
    app = build_outfit_panel_sidecar(
        OutfitPanelSidecarConfig(
            static_dir=_required_env("MILOCO_OUTFIT_PANEL_STATIC_DIR"),
            workspace_dir=_required_env("MILOCO_OUTFIT_PANEL_WORKSPACE"),
            primary_person_id=_required_env("MILOCO_OUTFIT_PANEL_PRIMARY_PERSON_ID"),
            token=_required_env("MILOCO_OUTFIT_PANEL_TOKEN"),
            browser_username=_required_env("MILOCO_OUTFIT_PANEL_BROWSER_USERNAME"),
            browser_password=_required_env("MILOCO_OUTFIT_PANEL_BROWSER_PASSWORD"),
        )
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be configured")
    return value


if __name__ == "__main__":
    start_outfit_panel_sidecar()
