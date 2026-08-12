# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Safe synthetic-host composition for the optional Outfit plugin.

This adapter is deliberately separate from ``miloco.main``. It lets a later
reviewed host integration install only the authenticated, owner-bound Outfit
surface after configuration and persistence construction have both succeeded.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI

from miloco.life.outfit_installation import (
    OutfitInstallConfig,
    OutfitInstallResult,
    OutfitRuntimeContext,
    install_outfit_plugin_if_enabled,
)
from miloco.middleware.auth_middleware import verify_token

_CAPABILITY_ROUTER_STATE = "outfit_capability_router_registered"


def install_outfit_host_composition(
    app: FastAPI,
    *,
    config: OutfitInstallConfig,
    clock_ms: Callable[[], int],
    authenticate: Callable[..., object] = verify_token,
) -> OutfitInstallResult:
    """Compose the optional Outfit HTTP surface into a supplied host.

    The capability snapshot is published under ``/api`` only after the
    controlled installer has built configured persistence successfully. The
    disabled and failed states intentionally expose no Outfit routes.
    """

    def install_authenticated_moment_router(
        host: FastAPI,
        context: OutfitRuntimeContext,
    ) -> None:
        from miloco.life.outfit_authenticated_router import (
            build_authenticated_outfit_moment_router,
        )
        from miloco.life.outfit_moment_runtime import build_outfit_moment_runtime

        runtime = build_outfit_moment_runtime(context, clock_ms=clock_ms)
        host.include_router(
            build_authenticated_outfit_moment_router(
                runtime,
                authenticate=authenticate,
            ),
            prefix="/api",
        )

    result = install_outfit_plugin_if_enabled(
        app,
        config=config,
        installer=install_authenticated_moment_router,
    )
    if result.installed:
        _install_capability_router_once(app, authenticate=authenticate)
    return result


def _install_capability_router_once(
    app: FastAPI,
    *,
    authenticate: Callable[..., object],
) -> None:
    """Register the low-sensitivity capability snapshot once per host."""
    if getattr(app.state, _CAPABILITY_ROUTER_STATE, False):
        return

    from miloco.life.outfit_capability_router import build_outfit_capability_router

    app.include_router(
        build_outfit_capability_router(app, authenticate=authenticate),
        prefix="/api",
    )
    setattr(app.state, _CAPABILITY_ROUTER_STATE, True)
